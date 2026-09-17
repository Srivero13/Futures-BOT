"""Fixed normalized-decline experiment. Offline execution; no forecast promotion."""
import argparse
from collections import deque
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys

import numpy as np
from backtest_v16 import Costs, D, simulate
from engine_v1.dataset import candles, sha256
from engine_v1.model import feature_matrix
from engine_v1.operations import atomic_json, process_lock
from train_v15 import timestamp
from walkforward_v16 import folds

HORIZON = 15
GRID_MS = HORIZON*60000
FLOOR = 1e-6
QUANTILE = .99


def decline_score(x):
    x=np.asarray(x,dtype=float)
    if x.shape!=(6,) or not np.isfinite(x).all() or x[3]<0:
        raise ValueError('Invalid causal features')
    return float(-x[2]/(max(float(x[3]),FLOOR)*math.sqrt(20)))


def threshold_from_scores(scores):
    a=np.asarray(scores,dtype=float)
    if a.ndim!=1 or not 100<=len(a)<=100000 or not np.isfinite(a).all():
        raise ValueError('Require 100..100000 finite calibration scores')
    return max(0.,float(np.quantile(a,QUANTILE)))


def calibrate(rows,start,end):
    if start>=end or start%GRID_MS or end%GRID_MS:
        raise ValueError('Calibration boundaries must align with the 15-minute grid')
    history=deque(maxlen=21)
    previous=None
    scores=[]
    for row in rows:
        ts=row['timestamp']
        if ts>=end:break
        if previous is not None and ts-previous!=60000:history.clear()
        history.append(row);previous=ts
        decision=ts+60000
        if start<=decision<end and decision%GRID_MS==0 and len(history)==21:
            scores.append(decline_score(feature_matrix(list(history))[-1]))
    expected=(end-start)//GRID_MS
    if len(scores)!=expected:
        raise ValueError(f'Incomplete calibration grid: {len(scores)}/{expected}; check gaps and preceding warm-up data')
    return {'threshold':threshold_from_scores(scores),'quantile':QUANTILE,
            'grid_examples':len(scores),'positive_decline_scores':sum(s>0 for s in scores),
            'start_ms':start,'end_ms':end}


@dataclass(frozen=True)
class ResearchSpec:
    calibration_end_ms:int
    horizon_bars:int=HORIZON
    timeframe_ms:int=60000


def evaluate(rows,start,end,calibration,progress=None):
    threshold=calibration['threshold']
    if not math.isfinite(threshold) or threshold<0:
        raise ValueError('Invalid calibrated score threshold')
    if start<calibration['end_ms']:
        raise ValueError('Test must follow calibration')
    def rule(x,ts):
        return ts%GRID_MS==0 and decline_score(x)>threshold
    report=simulate(rows,ResearchSpec(calibration['end_ms']),start,end,Costs(),progress,entry_rule=rule)
    summary=report['summary']
    summary['rule_candidates']=summary.pop('cost_gate_candidates')
    summary['reference_cost_plus_margin_log_bps']=summary.pop('entry_threshold_log_bps')
    summary.pop('ood_rejected')
    summary['entry_policy']='normalized decline above preceding-month 99th percentile; no forecast cost gate'
    report['calibration']=calibration
    report['limitations']=[s for s in report['limitations'] if 'forecasts were trained' not in s]
    report['limitations'].extend([
        'The rule is not a return forecast: no model OOD filter, forecast lower bound or cost entry gate is used.',
        'Costs are charged on every simulated fill; positive score does not imply expected profit above costs.',
        'One-minute entry delay, 15-minute holding period from fill, decisions on the fixed UTC 15-minute grid.',
        'Prices/volumes flagged by the data audit are retained. No stop loss or live portfolio policy is added.'])
    return report


def run(paths,symbol,first_test,months,reserve_from,output):
    schedule=folds(first_test,months)
    reserve=timestamp(reserve_from)
    if timestamp(schedule[-1]['test_end'])>reserve:
        raise ValueError('Development folds cross reserved date')
    output=Path(output)
    if output.exists():raise ValueError('Output exists; choose a new filename')
    paths=[Path(p).resolve() for p in paths]
    if not paths or len(set(paths))!=len(paths):raise ValueError('Supply unique chronological shards')
    sources=[]
    print('[reversal] verifying inputs',flush=True)
    for path in paths:
        meta=json.loads(path.with_suffix('.json').read_text())
        if type(meta.get('last_open_ms')) is not int or meta['last_open_ms']>=reserve:
            raise ValueError('Shard has missing range metadata or enters reserved dates')
        digest=sha256(path)
        if (meta.get('sha256'),meta.get('venue'),meta.get('symbol'),meta.get('timeframe_ms'))!=(digest,'binance',symbol,60000):
            raise ValueError(f'Shard provenance mismatch: {path}')
        sources.append({'file':str(path),'sha256':digest})
    protocol={'symbol':symbol,'schedule':schedule,'reserve_from':reserve_from,
        'horizon_minutes':HORIZON,'grid_ms':GRID_MS,'volatility_floor':FLOOR,
        'score':'-momentum_20 / (max(volatility_20, 0.000001) * sqrt(20))',
        'threshold':'max(0, calibration 99th percentile); strict greater-than entry',
        'costs':asdict(Costs()),'sources':sources,
        'code_sha256':{str(p):sha256(p) for p in [Path(__file__),Path(__file__).parent/'backtest_v16.py',
             Path(__file__).parent/'engine_v1'/'model.py',Path(__file__).parent/'engine_v1'/'dataset.py']}}
    protocol_path=output.with_suffix('.protocol.json')
    if protocol_path.exists():
        if json.loads(protocol_path.read_text())!=protocol:
            raise ValueError('Saved protocol differs; use a new output path')
    else:atomic_json(protocol_path,protocol)
    reports=[]
    for i,fold in enumerate(schedule,1):
        print(f'[reversal] fold {i}/{months}: calibration {fold["train_end"]}; test {fold["calibration_end"]}',flush=True)
        cal=calibrate(candles(paths),timestamp(fold['train_end']),timestamp(fold['calibration_end']))
        print(f'[reversal] threshold={cal["threshold"]:.6f}, calibration examples={cal["grid_examples"]}',flush=True)
        report=evaluate(candles(paths),timestamp(fold['calibration_end']),timestamp(fold['test_end']),cal,
            lambda bars,trades:print(f'[reversal] bars={bars:,} trades={trades}',flush=True))
        report['test_start']=fold['calibration_end'];report['test_end']=fold['test_end']
        reports.append(report)
        print('[reversal] result: '+json.dumps(report['summary']),flush=True)
    if any(sha256(p)!=s['sha256'] for p,s in zip(paths,sources)):
        raise ValueError('Inputs changed during experiment')
    totals=[D(r['summary']['net_pnl']) for r in reports]
    summary={'folds':len(reports),'closed_trades':sum(r['summary']['closed_trades'] for r in reports),
        'positive_pnl_months':sum(p>0 for p in totals),
        'sum_independent_month_net_pnl':str(sum(totals,D(0))),
        'monthly':[{'month':r['test_start'][:7],
                    **{k:r['summary'][k] for k in ('closed_trades','net_pnl','fees','spread_slippage_cost','max_drawdown_pct')},
                    'score_threshold':r['calibration']['threshold']} for r in reports],
        'note':'Each month resets to 1000 quote-currency units; summed P&L is not a compounded portfolio return.'}
    result={'approved':False,'protocol':protocol,'summary':summary,'folds':reports,
            'note':'Retrospective fixed-rule execution experiment, not significance or promotion. Reserved period excluded.'}
    atomic_json(output,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files',nargs='+',type=Path,required=True)
    p.add_argument('--symbol',required=True)
    p.add_argument('--first-test',required=True)
    p.add_argument('--months',type=int,default=6)
    p.add_argument('--reserve-from',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        with process_lock(a.output.with_suffix('.lock')):
            report=run(a.files,a.symbol,a.first_test,a.months,a.reserve_from,a.output)
        print(json.dumps(report['summary'],indent=2))
        print(f'Completed: {a.output}; research-only, unapproved.')
        return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
        print(f'Reversal experiment stopped: {error}',file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('Interrupted; no complete aggregate report published.',file=sys.stderr);return 130


if __name__=='__main__':raise SystemExit(main())
