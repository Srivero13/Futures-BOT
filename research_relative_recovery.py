"""One fixed ETH-relative-to-BTC recovery rule; retrospective development only."""
import argparse
from collections import deque
from dataclasses import asdict
from decimal import localcontext
from itertools import zip_longest
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from backtest_v16 import Costs, D, simulate
from engine_v1.dataset import candles, sha256
from engine_v1.operations import atomic_json, process_lock
from research_cross_asset import verify
from research_daily_breakout import summarize
from train_v15 import timestamp
from walkforward_v16 import folds

MINUTE=60000
WINDOW=1501


def movement_floor():
    c=Costs();f=c.fee_bps/10000;i=(c.spread_bps/2+c.slippage_bps)/10000
    return 2*(math.log1p(f)-math.log1p(-f)+math.log1p(i)-math.log1p(-i))


def signal_details(eth,btc):
    e,b=np.asarray(eth,dtype=float),np.asarray(btc,dtype=float)
    if e.shape!=(WINDOW,) or b.shape!=(WINDOW,) or not np.isfinite([e,b]).all() or min(e.min(),b.min())<=0:
        raise ValueError('Require 1501 finite positive aligned closes')
    er=np.diff(np.log(e[::60]));br=np.diff(np.log(b[::60]))
    # Fit only the 24 hours preceding the latest hour; exclude the event hour.
    x,y=br[:-1],er[:-1]
    variance=float(np.sum((x-x.mean())**2))
    if variance<=1e-12:return {'enter':False,'reason':'insufficient_btc_variation'}
    beta=float(np.sum((x-x.mean())*(y-y.mean()))/variance)
    intercept=float(y.mean()-beta*x.mean())
    residuals=y-intercept-beta*x
    sigma=max(float(np.sqrt(np.sum(residuals**2)/(len(x)-2))),1e-6)
    residual=float(er[-1]-intercept-beta*br[-1])
    recovery=math.log(float(e[-1]))-math.log(float(e[-6]))
    z=residual/sigma
    return {'enter':bool(beta>0 and br[-1]>=0 and z < -2 and
                         residual < -movement_floor() and recovery>0),
            'beta':beta,'residual_z':z,'residual_log_bps':residual*10000,
            'btc_last_hour_log_bps':float(br[-1]*10000),
            'eth_last_five_minutes_log_bps':recovery*10000}


def build_signals(eth_rows,btc_rows,start,end):
    window=deque(maxlen=WINDOW);previous=None;signals={};count=0
    for e,b in zip_longest(eth_rows,btc_rows):
        if e is None or b is None or e['timestamp']!=b['timestamp']:
            raise ValueError('ETH/BTC coverage differs; no silent joins')
        ts=e['timestamp']
        if ts>=end:raise ValueError('Input enters reserved period')
        if previous is not None and ts!=previous+MINUTE:window.clear()
        previous=ts;window.append((e['close'],b['close']));count+=1
        if count%131072==0:print(f'[relative-recovery] aligned minutes={count:,}',flush=True)
        decision=ts+MINUTE
        if start<=decision<end and decision%(60*MINUTE)==0:
            if len(window)!=WINDOW:raise ValueError('Insufficient contiguous causal warmup')
            pairs=np.asarray(window,dtype=float)
            signals[decision]=signal_details(pairs[:,0],pairs[:,1])
    expected=(end-start)//(60*MINUTE)
    if len(signals)!=expected:raise ValueError('Incomplete hourly decision grid')
    return signals


def evaluate(rows,signals,start,end,progress=None):
    spec=SimpleNamespace(calibration_end_ms=start,horizon_bars=60,timeframe_ms=MINUTE)
    result=simulate(rows,spec,start,end,Costs(),progress,
                    entry_rule=lambda x,ts:bool(signals.get(ts,{}).get('enter',False)))
    result['summary']['rule_candidates']=result['summary'].pop('cost_gate_candidates')
    result['summary']['reference_cost_plus_margin_log_bps']=result['summary'].pop('entry_threshold_log_bps')
    result['summary'].pop('ood_rejected')
    result['summary']['entry_policy']='Fixed causal BTC-conditioned residual recovery; no forecast gate'
    with localcontext() as context:
        context.prec=50
        c=Costs();f=D(c.fee_bps)/10000;i=(D(c.spread_bps)/2+D(c.slippage_bps))/10000
        stress={}
        for extra in ('0','0.5','1','2'):
            impact=i+D(extra)/10000
            net=sum((D(t['quantity'])*(D(t['exit_price'])/(1-i)*(1-impact)*(1-f)
                   -D(t['entry_price'])/(1+i)*(1+impact)*(1+f)) for t in result['trades']),D(0))
            stress[extra]=str(net)
        if abs(D(stress['0'])-D(result['summary']['net_pnl']))>D('1e-25'):
            raise ValueError('Stress accounting does not reconcile')
        result['summary']['fixed_quantity_extra_slippage_bps_per_side']=stress
    for trade in result['trades']:
        trade['causal_signal']=signals[trade['decision_ms']]
    result['limitations']=[s for s in result['limitations'] if 'forecasts were trained' not in s]
    return result


def run(eth,btc,output):
    output=Path(output);plan=output.with_suffix('.protocol.json')
    if output.exists() or plan.exists():raise ValueError('Choose new output/protocol paths')
    start,end=timestamp('2026-03-01'),timestamp('2026-09-01')
    eth,es=verify(eth,'ETHUSDT',end);btc,bs=verify(btc,'BTCUSDT',end)
    root=Path(__file__).resolve().parent
    protocol={'hypothesis':'Temporary ETH underperformance relative to non-falling BTC may recover after ETH turns upward',
        'market':'binance_spot','traded_symbol':'ETHUSDT','context_symbol':'BTCUSDT',
        'schedule':folds('2026-03-01',6),'reserve_from':'2026-09-01','experiment_budget':1,
        'parameters':{'fit_prior_hours':24,'event_hours':1,'residual_z_below':-2,
                      'residual_below_negative_roundtrip_cost_multiple':2,
                      'positive_beta_required':True,'btc_hour_return_minimum':0,
                      'eth_recovery_minutes':5,'eth_recovery_return_strictly_positive':True,
                      'decision_grid_minutes':60,'entry_delay_minutes':1,'hold_minutes':60,
                      'btc_centered_sum_squares_floor':1e-12,'residual_sigma_floor':1e-6},
        'costs':asdict(Costs()),'sources':es+bs,
        'code_sha256':{name:sha256(root/name) for name in
            ('research_relative_recovery.py','backtest_v16.py','research_daily_breakout.py',
             'research_cross_asset.py','engine_v1/dataset.py','engine_v1/model.py',
             'engine_v1/operations.py','train_v15.py','walkforward_v16.py')}}
    atomic_json(plan,protocol)
    signals=build_signals(candles(eth),candles(btc),start,end)
    print(f'[relative-recovery] fixed rule matches={sum(s["enter"] for s in signals.values())}/{len(signals)}',flush=True)
    reports=[]
    for fold in protocol['schedule']:
        print('[relative-recovery] month='+fold['calibration_end'],flush=True)
        result=evaluate(candles(eth),signals,timestamp(fold['calibration_end']),timestamp(fold['test_end']),
                        lambda bars,trades:print(f'[relative-recovery] bars={bars:,} trades={trades}',flush=True))
        result.update(test_start=fold['calibration_end'],test_end=fold['test_end'])
        reports.append(result)
    for source in es+bs:
        if sha256(source['path'])!=source['sha256'] or sha256(source['sidecar'])!=source['sidecar_sha256']:
            raise ValueError('Source changed during research')
    summary=summarize(reports)
    atomic_json(output,{'approved':False,'protocol':protocol,'summary':summary,'folds':reports,
        'hourly_rule_matches':sum(s['enter'] for s in signals.values()),
        'limitations':['Retrospective development on already inspected months; no independent validation.',
            'One discretionary fixed hypothesis, no parameter sweep; prior failed studies remain part of research history.',
            'BTC is context only, not a hedge. ETH spot exposure remains directional.',
            'Past relative deviation is not a forecast of recovery or expected profit.',
            'Full fills, fixed costs, monthly capital resets; no stops or intrabar risk measurement.',
            'Small rolling regressions can be unstable. No confidence/significance claims or model approval.',
            'Passing the development screens would still require fresh independent validation.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--eth',nargs='+',type=Path,required=True)
    p.add_argument('--btc',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        with process_lock(str(a.output)+'.lock'):result=run(a.eth,a.btc,a.output)
        print(json.dumps(result,indent=2))
        print(f'Completed: {a.output}; research-only, unapproved.')
    except (ValueError,OSError,KeyError,TypeError) as error:p.exit(2,f'Relative recovery stopped: {error}\n')


if __name__=='__main__':main()
