"""Fixed paired candle/flow research; no executable or approved model is produced."""
import argparse
from collections import deque
import csv
import json
from pathlib import Path
import sys
import numpy as np
from engine_v1.dataset import examples, sha256
from engine_v1.operations import atomic_json
from train_v15 import timestamp
from walkforward_v16 import ranking, shift_month


def flow_features(paths):
    """Key features by availability, never by the opening time of the minute."""
    result = {}; window = deque(maxlen=20); previous = None
    for path in paths:
        with Path(path).open(newline='') as handle:
            for row in csv.DictReader(handle):
                opened = int(row['timestamp'])*1000
                available = int(row['available_at_ms'])
                if available != opened+60000 or opened % 60000 or (previous is not None and opened <= previous):
                    raise ValueError('Unordered or invalid flow availability')
                if previous is not None and opened != previous+60000:
                    window.clear()
                previous = opened
                buy, sell = float(row['taker_buy_quote']), float(row['taker_sell_quote'])
                events = int(row['agg_events'])
                if not np.isfinite([buy,sell]).all() or min(buy,sell)<0 or buy+sell<=0 or events<=0:
                    raise ValueError('Invalid flow notional/events')
                window.append((buy-sell,buy+sell,events))
                if len(window)==20:
                    data=np.asarray(window); short=data[-5:].sum(axis=0); long=data.sum(axis=0)
                    result[available]=[short[0]/short[1],long[0]/long[1],4*short[2]/long[2]]
    return result


def fit_predict(train_x, train_y, targets, alpha=10.):
    mean=train_x.mean(axis=0); scale=train_x.std(axis=0); scale[scale<1e-12]=1.
    x=np.column_stack((np.ones(len(train_x)),(train_x-mean)/scale))
    penalty=np.eye(x.shape[1])*np.sqrt(alpha); penalty[0,0]=0
    coef=np.linalg.lstsq(np.vstack((x,penalty)),np.r_[train_y,np.zeros(x.shape[1])],rcond=None)[0]
    return [np.column_stack((np.ones(len(t)),(t-mean)/scale))@coef for t in targets]


def run(a):
    output=Path(a.output)
    if output.exists():raise ValueError('Output exists; choose a new name')
    boundaries=[timestamp(shift_month(a.start,i)) for i in range(4)]
    if boundaries[-1]>timestamp(a.reserve_from):raise ValueError('Experiment crosses reserved boundary')
    fingerprints={}; flow_paths=[]; candle_paths=set(); audited_days=set()
    for audit_path in a.audits:
        audit_path=Path(audit_path).resolve(); report=json.loads(audit_path.read_text())
        if not report['summary']['alignment_passed'] or report['spec']['symbol']!=a.symbol:
            raise ValueError('Require passing alignment audits for this symbol')
        for day in report['days']:
            if day in audited_days:raise ValueError('Duplicate audited day')
            audited_days.add(day)
        fingerprints[str(audit_path)]=sha256(audit_path)
        for name,digest in report['spec']['input_sha256'].items():
            path=Path(name)
            if not path.is_absolute():raise ValueError('Audit paths must be absolute')
            if name in fingerprints and fingerprints[name]!=digest:raise ValueError('Conflicting audit hashes')
            fingerprints[name]=digest
            if name.endswith('-flow.csv'):flow_paths.append(path)
            elif name.endswith('.csv'):candle_paths.add(path)
    required=set(range(boundaries[0],boundaries[-1],86400000))
    if {timestamp(day) for day in audited_days}!=required:
        raise ValueError('Audits must cover exactly three consecutive complete months')
    def verify():
        for name,digest in fingerprints.items():
            if sha256(Path(name))!=digest:raise ValueError('Audited input changed: '+name)
    print('[flow-research] verifying audited inputs',flush=True);verify()
    protocol={'symbol':a.symbol,'start':a.start,'reserve_from':a.reserve_from,'horizon_minutes':15,
        'alpha':10,'train_end_ms':boundaries[1],'calibration_end_ms':boundaries[2],'test_end_ms':boundaries[3],
        'features':['notional_imbalance_5','notional_imbalance_20','event_activity_5_vs_20'],
        'input_sha256':fingerprints,'code_sha256':{str(p):sha256(p) for p in [Path(__file__),
            Path(__file__).parent/'walkforward_v16.py',Path(__file__).parent/'engine_v1/dataset.py',
            Path(__file__).parent/'engine_v1/model.py']}}
    plan=output.with_suffix('.protocol.json')
    if plan.exists() and json.loads(plan.read_text())!=protocol:raise ValueError('Saved protocol differs')
    atomic_json(plan,protocol)
    print('[flow-research] building closed-minute features',flush=True)
    flow=flow_features(sorted(flow_paths))
    splits=[[],[],[]]; missing=0
    for batch in examples(sorted(candle_paths),horizon=15):
        for row in batch:
            t,end=int(row[0]),int(row[1])
            if t//60000%15:continue
            for i in range(3):
                if boundaries[i]<=t and end<boundaries[i+1]:
                    if t not in flow:missing+=1;break
                    splits[i].append([*row[2:8],*flow[t],row[8]])
                    break
    if missing:raise ValueError('Missing flow features on paired grid')
    if min(map(len,splits))<100:raise ValueError('Insufficient paired rows')
    train,cal,test=map(np.asarray,splits)
    print('[flow-research] paired rows: '+str(list(map(len,splits))),flush=True)
    metrics={}
    for name,width in [('candles_only',6),('candles_plus_flow',9)]:
        print('[flow-research] fitting '+name,flush=True)
        cp,tp=fit_predict(train[:,:width],train[:,-1],[cal[:,:width],test[:,:width]])
        metrics[name]=ranking(np.column_stack((cp,cal[:,-1])),np.column_stack((tp,test[:,-1])))
    verify()
    summary={'paired_rows':dict(zip(['train','calibration','test'],map(len,splits))),
        'test_rmse_log_bps':{k:v['rmse_log_bps'] for k,v in metrics.items()},
        'zero_rmse_log_bps':metrics['candles_only']['zero_rmse_log_bps_same_rows'],
        'test_spearman':{k:v['spearman'] for k,v in metrics.items()},
        'flow_minus_candle_rmse_log_bps':metrics['candles_plus_flow']['rmse_log_bps']-metrics['candles_only']['rmse_log_bps']}
    atomic_json(output,{'approved':False,'pnl':None,'protocol':protocol,'summary':summary,'rankings':metrics,
        'limitations':['One development split; not independent evidence of profitability or significance.',
        'Fixed 15-minute UTC grid, boundary labels purged; serial dependence remains.',
        'Scaling and ridge fitting use first month only; bucket cuts use second month only.',
        'Features use closed minutes in event time; live receipt delay and fills are not modeled.',
        'No OOD filtering; both models use identical rows. No cost or execution backtest.',
        'No model exported, selected or approved. September and later remain reserved.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audits',nargs='+',required=True,type=Path)
    p.add_argument('--symbol',required=True);p.add_argument('--start',required=True)
    p.add_argument('--reserve-from',required=True);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    try:
        print(json.dumps(run(a),indent=2));print(f'Completed: {a.output}; research-only, unapproved.')
    except (ValueError,OSError,KeyError,TypeError,csv.Error) as error:
        print(f'Flow research stopped: {error}',file=sys.stderr);return 2
    except KeyboardInterrupt:return 130
    return 0


if __name__=='__main__':raise SystemExit(main())
