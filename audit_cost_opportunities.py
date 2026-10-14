"""Fixed development-only cost hurdle audit; no forecast, signal, or trade selection."""
import argparse
from collections import deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import numpy as np
from engine_v1.dataset import candles, sha256
from engine_v1.operations import atomic_json, process_lock
from research_cross_asset import verify
from train_v15 import timestamp

MINUTE=60000
HORIZONS=(15,60)
COSTS={'fee_bps_per_side':10,'full_spread_bps':2,'slippage_bps_per_side':2}


def barrier():
    fee=COSTS['fee_bps_per_side']/10000
    impact=(COSTS['full_spread_bps']/2+COSTS['slippage_bps_per_side'])/10000
    return 10000*(math.log1p(fee)-math.log1p(-fee)+math.log1p(impact)-math.log1p(-impact))


def metrics(values):
    a=np.asarray(values,dtype=float)
    if not len(a):raise ValueError('No complete paired observations')
    if not np.isfinite(a).all():raise ValueError('Non-finite reference returns')
    cost=barrier()
    with np.errstate(over='raise',invalid='raise'):
        try:net=np.expm1((a-cost)/10000)*10000
        except FloatingPointError as error:raise ValueError('Reference return exceeds numeric range') from error
    return {'observations':len(a),'positive_reference_moves':int(np.sum(a>0)),
        'moves_above_cost':int(np.sum(a>cost)),
        'moves_above_cost_pct':float(np.mean(a>cost)*100),
        'mean_reference_log_bps':float(a.mean()),
        'median_reference_log_bps':float(np.median(a)),
        'p95_reference_log_bps':float(np.quantile(a,.95)),
        'mean_long_return_after_assumed_cost_bps':float(net.mean()),
        'note':'Every fixed-grid observation, without selection; descriptive returns, not portfolio P&L.'}


def audit(rows,start,end,progress=None):
    if start>=end or start%MINUTE or end%MINUTE:raise ValueError('Invalid interval')
    window=deque(maxlen=62)
    observed=0; previous=None; monthly={}; purged=0
    for row in rows:
        ts=row['timestamp']
        if ts>=end:raise ValueError('Input enters reserved interval')
        if ts<start:continue
        if ts!=(start if previous is None else previous+MINUTE):
            raise ValueError('Missing or unordered development minute')
        previous=ts;observed+=1;window.append(row)
        if progress and observed%32768==0:progress(observed)
        if len(window)!=62:continue
        decision=window[0]['timestamp']
        if decision%(60*MINUTE):continue
        month=datetime.fromtimestamp(decision/1000,timezone.utc).strftime('%Y-%m')
        last_month=datetime.fromtimestamp(ts/1000,timezone.utc).strftime('%Y-%m')
        if month!=last_month:
            purged+=1
            continue
        entry=float(window[1]['open'])
        if not math.isfinite(entry) or entry<=0:raise ValueError('Invalid entry reference')
        grouped=monthly.setdefault(month,{str(h):[] for h in HORIZONS})
        for h in HORIZONS:
            exit_price=float(window[1+h]['open'])
            if not math.isfinite(exit_price) or exit_price<=0:raise ValueError('Invalid exit reference')
            # Log differences avoid overflow when dividing extreme valid prices.
            grouped[str(h)].append((math.log(exit_price)-math.log(entry))*10000)
    if observed!=(end-start)//MINUTE:raise ValueError('Incomplete development coverage')
    summary={str(h):metrics([v for values in monthly.values() for v in values[str(h)]]) for h in HORIZONS}
    return {'observed_minutes':observed,'cost_barrier_log_bps':barrier(),
        'paired_observations':summary['15']['observations'],
        'month_boundary_anchors_purged':purged,
        'horizons':summary,
        'monthly':{month:{h:metrics(values) for h,values in horizons.items()}
                   for month,horizons in monthly.items()}}


def run(paths,output):
    output=Path(output)
    protocol_path=output.with_suffix('.protocol.json')
    if output.exists() or protocol_path.exists():raise ValueError('Choose new output and protocol paths')
    start,end=timestamp('2026-03-01'),timestamp('2026-09-01')
    print('[cost-audit] verifying development sources',flush=True)
    paths,sources=verify(paths,'ETHUSDT',end)
    root=Path(__file__).resolve().parent
    protocol={'study':'Unconditional development cost feasibility; one fixed descriptive audit',
        'symbol':'ETHUSDT','market':'spot','start':'2026-03-01','end':'2026-09-01',
        'reserve_from':'2026-09-01','decision_grid_minutes':60,'entry_delay_minutes':1,
        'holding_minutes':list(HORIZONS),'costs':COSTS,
        'paired_policy':'Both outcomes must finish within the same calendar month',
        'experiment_budget':1,'sources':sources,
        'code_sha256':{name:sha256(root/name) for name in
            ('audit_cost_opportunities.py','engine_v1/dataset.py','research_cross_asset.py','train_v15.py')}}
    atomic_json(protocol_path,protocol)
    result=audit(candles(paths),start,end,
                 lambda n:print(f'[cost-audit] evaluated minutes={n:,}',flush=True))
    for source in sources:
        if sha256(source['path'])!=source['sha256'] or sha256(source['sidecar'])!=source['sidecar_sha256']:
            raise ValueError('Source changed during audit')
    atomic_json(output,{'approved':False,'pnl':None,'protocol':protocol,'summary':result,
        'limitations':[
            'Already inspected development months; not independent validation.',
            'Future returns are outcomes only, never an entry signal.',
            'One-minute candle opens are reference prices, not executable bid/ask quotes.',
            'Assumed constant costs; no queue, fill, size, liquidity or portfolio simulation.',
            'No confidence intervals or predictive model; serial dependence remains.',
            'No short selling, model promotion, reserved data access or automatic follow-on search.']})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files',nargs='+',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    try:
        with process_lock(str(args.output)+'.lock'):
            result=run(args.files,args.output)
        print(json.dumps(result,indent=2))
        print(f'Completed: {args.output}; descriptive audit only, unapproved.')
    except (ValueError,OSError,KeyError,TypeError) as error:
        parser.exit(2,f'Cost audit stopped: {error}\n')


if __name__=='__main__':main()
