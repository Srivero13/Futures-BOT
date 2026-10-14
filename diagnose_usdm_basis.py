"""Fixed descriptive spot/futures candle-basis study; no executable prices or P&L."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path

import numpy as np
from audit_usdm_pilot import audit
from engine_v1.dataset import candles, sha256


def describe(values):
    a = np.asarray(values, dtype=float)
    return dict(count=len(a), mean=float(a.mean()), min=float(a.min()),
                max=float(a.max()), **{f'p{p:02d}':float(np.percentile(a,p)) for p in (5,50,95)})


def analyze(spot, futures):
    if len(spot) != len(futures) or len(spot) < 61:
        raise ValueError('Require matching series with at least 61 minutes')
    times = []
    prices = [[], []]
    for i, (s, f) in enumerate(zip(spot, futures)):
        t = s['timestamp']
        if (type(t) is not int or t % 60000 or type(f['timestamp']) is not int
                or f['timestamp'] != t or (times and t != times[-1]+60000)):
            raise ValueError('Require identical continuous minute timestamps')
        times.append(t)
        for bucket, row in zip(prices, (s, f)):
            value = float(row['close'])
            if not np.isfinite(value) or value <= 0:
                raise ValueError('Require finite positive close prices')
            bucket.append(value)
    basis = (np.log(prices[1])-np.log(prices[0]))*10000
    # Same hourly anchors and maximum horizon for both comparisons; no selection.
    anchors = np.array([i for i,t in enumerate(times)
                        if t % 3600000 == 0 and i+60 < len(times)], dtype=int)
    if not len(anchors):
        raise ValueError('No complete hourly anchors')
    horizons = {}
    for horizon in (15,60):
        change = basis[anchors+horizon]-basis[anchors]
        start = basis[anchors]
        corr = (float(np.corrcoef(start,change)[0,1])
                if np.std(start)>1e-12 and np.std(change)>1e-12 else None)
        horizons[str(horizon)] = dict(
            basis_change_log_bps=describe(change),
            pearson_initial_basis_vs_change_descriptive=corr,
            strictly_closer_to_zero_count=int(np.sum(np.abs(basis[anchors+horizon])<np.abs(start))))
    return dict(minutes=len(times),basis_log_bps=describe(basis),
                paired_hourly_anchors=len(anchors),horizons_minutes=horizons)


def run(first, batch, spot_root):
    start=date(2026,8,1); reserve=date(2026,9,1)
    spot_path=Path(spot_root)/'binance-ETHUSDT-2026-08.csv'
    sources={}; future_rows=[]
    for i in range(7):
        day=start+timedelta(days=i)
        folder=Path(first) if i==0 else Path(batch)/str(day)
        print(f'[basis] auditing day {i+1}/7: {day}',flush=True)
        report=audit(folder,spot_path,'ETHUSDT',day,reserve)
        for path,digest in report['inputs_sha256'].items():
            if path in sources and sources[path]!=digest:
                raise ValueError('Shared source changed during audits')
            sources[path]=digest
        future_rows.extend(candles([folder/f'binance-usdm-ETHUSDT-{day}.csv']))
    begin,end=future_rows[0]['timestamp'],future_rows[-1]['timestamp']
    spot_rows=[r for r in candles([spot_path]) if begin<=r['timestamp']<=end]
    if len(future_rows)!=10080:
        raise ValueError('Expected exactly seven complete days')
    summary=analyze(spot_rows,future_rows)
    if any(sha256(p)!=h for p,h in sources.items()):
        raise ValueError('Inputs changed during basis calculation')
    return dict(approved=False,experiment='BASIS-D01',status='descriptive_only',
                symbol='ETHUSDT',start='2026-08-01',end_exclusive='2026-08-08',
                summary=summary,inputs_sha256=sources,
                code_sha256={n:sha256(Path(__file__).parent/n) for n in
                    ('diagnose_usdm_basis.py','audit_usdm_pilot.py','download_usdm_pilot.py',
                     'engine_v1/dataset.py','research_cross_asset.py')},
                limitations=[
                    'Previously inspected development dates, not independent validation.',
                    'Candle closes may represent trades at different instants; timestamp alignment is not executable synchronization.',
                    'Basis is 10000 * (log futures close - log spot close); changes are not hedged portfolio returns.',
                    'Hourly anchors identified by candle open time; close values become available only at candle end.',
                    'No significance test, signal selection, funding, fees, spread, slippage, financing or liquidation accounting.',
                    'No strategy or model approval; September remains reserved.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('first-pilot','batch-root','spot-root','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Use a new output path')
    report=run(a.first_pilot,a.batch_root,a.spot_root)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as handle:
        json.dump(report,handle,indent=2,allow_nan=False);handle.write('\n')
    print(json.dumps(report['summary'],indent=2,allow_nan=False))
    print(f'Completed: {a.output}; descriptive only, unapproved.')


if __name__=='__main__': main()
