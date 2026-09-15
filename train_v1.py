"""April fit/calibration, May selection, June untouched holdout; 1-minute spot data."""
import csv
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import time
import numpy as np
from engine_v1.core import Quote,Portfolio,dec,break_even_bps,monetary
from engine_v1.model import feature_matrix,fit_model
ROOT=Path(__file__).resolve().parent


def load_rows(path):
    with path.open() as f:rows=list(csv.DictReader(f))
    last=None
    for r in rows:
        r['timestamp']=int(r['timestamp'])*1000
        ts=r['timestamp']
        if ts%60000 or (last is not None and ts-last!=60000):raise ValueError('Unordered, duplicate or missing 1m candle')
        values={k:dec(r[k]) for k in ('open','high','low','close','volume')}
        if min(values[k] for k in ('open','high','low','close'))<=0 or values['volume']<0:raise ValueError('Invalid OHLCV')
        if values['low']>min(values['open'],values['close']) or values['high']<max(values['open'],values['close']):raise ValueError('Invalid OHLC bounds')
        last=ts
    return rows


@monetary
def evaluate(rows,x,model,start,end,*,fees='10',slip='2',spread='2',latency_ms=250,strategy='model',include_daily=False):
    if not 0<=latency_ms<60000:raise ValueError('Replay supports latency below one candle')
    symbol=model.symbol;acc=[{'id':symbol,'symbol':symbol,'capital':'1000','notional':'100'}]
    engine=Portfolio(':memory:',acc,fee_bps=fees,slip_bps=slip,global_cap='100')
    latest_intent={};trades=[];hourly={};prior=dec('1000');peak=prior;maxdd=dec(0);timings=[];eligible=0
    for i in range(start,end):
        ref=dec(rows[i]['open']);ts=rows[i]['timestamp']+latency_ms
        half=dec(spread)/20000
        # OHLC cannot reproduce sub-minute book/latency: shock is a sensitivity proxy.
        vol=float(x[i-1][3]) if i>20 else 0.
        latency_shock=dec(str(vol*np.sqrt(latency_ms/60000)*10000))
        ask=ref*(1+half+latency_shock/10000);bid=ref*(1-half-latency_shock/10000)
        q=Quote(symbol,bid,ask,dec('1000000'),dec('1000000'),ts,i)
        cost=break_even_bps(q,fees,slip)
        t0=time.perf_counter_ns()
        if strategy=='cash':intent={'enter':False}
        elif strategy=='sma':intent={'enter':float(x[i-1][1])>0 and float(x[i-1][2])>0}
        else:intent=model.decision(x[i-1],cost)
        timings.append((time.perf_counter_ns()-t0)/1e6);eligible+=bool(intent.get('enter'))
        # Last point closes all inventory and prohibits new entries.
        if i==end-1:intent={'enter':False,'exit':True}
        events=engine.process({symbol:q},{symbol:intent},ts,event_id=f'bar:{i}',horizon_ms=model.horizon_bars*60000,cooldown_ms=60000)
        e=events[-1];eq=dec(e['equity']);hour=rows[i]['timestamp']//3600000
        hourly[hour]=hourly.get(hour,dec(0))+eq-prior;prior=eq;peak=max(peak,eq);maxdd=max(maxdd,(peak-eq)/peak)
        if e['action']!='HOLD':trades.append(e)
    state=engine.states()[0];engine.close()
    hours=(end-start)/60;pnl=dec(state['cash'])-dec('1000')
    realized=[];last=dec(0)
    for e in trades:
        if e['action']=='SELL':realized.append(dec(e['realized'])-last);last=dec(e['realized'])
    wins=sum((v for v in realized if v>0),dec(0));loss=-sum((v for v in realized if v<0),dec(0))
    summary={'symbol':symbol,'strategy':strategy,'horizon_minutes':model.horizon_bars,
        'start_ms':rows[start]['timestamp'],'end_ms':rows[end-1]['timestamp']+60000,
        'capital':'1000','notional':'100','net_pnl':str(pnl),'fees':state['fees'],'closed_trades':len(realized),
        'profit_factor':str(wins/loss) if loss else None,'max_drawdown_pct':str(maxdd*100),
        'average_pnl_per_hour':str(pnl/dec(str(hours))),'average_pnl_per_second':str(pnl/dec(str(hours*3600))),
        'worst_hour':str(min(hourly.values())),'best_hour':str(max(hourly.values())),
        'eligible_entry_bars':eligible,'signal_compute_p50_ms':float(np.quantile(timings,.5)),
        'signal_compute_p99_ms':float(np.quantile(timings,.99)),'latency_scenario_ms':latency_ms,
        'fee_bps':fees,'slippage_bps':slip,'spread_bps':spread,
        'warning':'Historical paper result; latency shock is an OHLC proxy, not observed execution.'}
    if include_daily:
        daily={}
        for hour,value in hourly.items():daily[hour//24]=daily.get(hour//24,dec(0))+value
        summary['daily_pnl']=[str(daily[k]) for k in sorted(daily)]
    return summary,trades


def main():
    root=ROOT/'reports/v1';root.mkdir(parents=True,exist_ok=True);(ROOT/'models').mkdir(exist_ok=True)
    report={'protocol':'April first 80% fit, final 20% error calibration, May horizon selection, June holdout. No retraining after May.',
        'candidates':[1,3,5],'datasets':{},'results':[],'models':{}}
    for symbol in ('BTCUSDT','ETHUSDT'):
        path=ROOT/'datasets'/f'{symbol}-1m-2025Q2.csv';rows=load_rows(path);x=feature_matrix(rows)
        may=next(i for i,r in enumerate(rows) if r['timestamp']>=1746057600000)
        june=next(i for i,r in enumerate(rows) if r['timestamp']>=1748736000000)
        report['datasets'][symbol]={'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        candidates=[]
        for h in (1,3,5):
            m=fit_model(rows,x,symbol,h,int(may*.8),may)
            s,_=evaluate(rows,x,m,may,june);candidates.append((m,s));print(symbol,h,'validation:',s['net_pnl'],s['closed_trades'],flush=True)
        m,validation=max(candidates,key=lambda pair:dec(pair[1]['net_pnl']))
        # Promotion requires enough net-positive validation evidence; not merely highest rank.
        m.approved=dec(validation['net_pnl'])>0 and validation['closed_trades']>=30 and m.calibration_rmse_bps<m.zero_forecast_rmse_bps
        m.save(ROOT/'models'/f'{symbol}-v1.json')
        report['models'][symbol]={'model':asdict(m),'validation_candidates':[s for _,s in candidates]}
        for name,kwargs in [('model_base',{}),('model_fast',{'latency_ms':50}),('model_slow',{'latency_ms':1000}),
                ('model_stress',{'fees':'15','slip':'5','spread':'10','latency_ms':1000}),
                ('baseline_momentum',{'strategy':'sma'}),('cash',{'strategy':'cash'})]:
            s,trades=evaluate(rows,x,m,june,len(rows),**kwargs);s['case']=name;report['results'].append(s)
            (root/f'{symbol}-{name}-trades.json').write_text(json.dumps(trades,indent=2))
            print(symbol,name,s['net_pnl'],flush=True)
    (root/'evaluation.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('Saved reports/v1/evaluation.json',flush=True)
if __name__=='__main__':main()
