"""Offline development-data quality and univariate feature audit; no model changes."""
import argparse
from collections import deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np
from engine_v1.dataset import candles, examples, segment, sha256
from engine_v1.model import FEATURES
from engine_v1.operations import atomic_json
from train_v15 import timestamp
from walkforward_v16 import average_ranks, correlation, shift_month


def month_name(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).strftime('%Y-%m')


def quality(rows,start,end,progress=None):
    months={}
    date=datetime.fromtimestamp(start/1000,timezone.utc).strftime('%Y-%m-%d')
    while timestamp(date)<end:
        next_date=shift_month(date,1)
        months[date[:7]]={'expected_minutes':(timestamp(next_date)-timestamp(date))//60000,
            'observed_minutes':0,'zero_volume':0,'large_close_moves':0,'large_open_jumps':0,
            'volume_spikes':0,'max_abs_close_move_log_bps':None,'max_abs_open_jump_log_bps':None,
            'max_volume_ratio':None}
        date=next_date
    previous=None
    volumes=deque(maxlen=20)
    samples=[]
    scanned=0
    for row in rows:
        ts=row['timestamp']
        if ts>=end:break
        scanned+=1
        contiguous=previous is not None and ts-previous['timestamp']==60000
        if not contiguous:volumes.clear()
        if ts>=start:
            m=months[month_name(ts)]
            m['observed_minutes']+=1
            volume=float(row['volume'])
            if volume==0:m['zero_volume']+=1
            checks=[]
            if contiguous:
                prior=math.log(float(previous['close']))
                close_move=abs(math.log(float(row['close']))-prior)*10000
                open_jump=abs(math.log(float(row['open']))-prior)*10000
                checks.extend([('large_close_moves','max_abs_close_move_log_bps',close_move,100),
                               ('large_open_jumps','max_abs_open_jump_log_bps',open_jump,100)])
            if len(volumes)==20 and sum(volumes)>0:
                ratio=volume/(sum(volumes)/20)
                checks.append(('volume_spikes','max_volume_ratio',ratio,20))
            for count_key,max_key,value,threshold in checks:
                m[max_key]=value if m[max_key] is None else max(m[max_key],value)
                if value>threshold:
                    m[count_key]+=1
                    if len(samples)<30:samples.append({'timestamp_ms':ts,'kind':count_key,'value':value})
        volumes.append(float(row['volume']))
        previous=row
        if progress and scanned%65536==0:progress(scanned)
    for m in months.values():
        m['missing_minutes']=m['expected_minutes']-m['observed_minutes']
    return {'monthly':months,'first_flagged_examples':samples,
            'thresholds':{'absolute_price_move_log_bps':100,'volume_vs_previous_20_mean':20},
            'note':'Flags request inspection, not deletion. Missing minutes include boundary gaps. Price moves only compare adjacent minutes.'}


def feature_month(rows):
    if not len(rows):return {'examples':0,'features':{}}
    y=rows[:,6]
    ranks=average_ranks(y)
    features={}
    for j,name in enumerate(FEATURES):
        x=rows[:,j]
        features[name]={'spearman':correlation(average_ranks(x),ranks),'pearson':correlation(x,y),
                        'mean':float(x.mean()),'std':float(x.std()),'min':float(x.min()),'max':float(x.max())}
    return {'examples':len(rows),'mean_target_log_bps':float(y.mean()),'features':features}


def feature_audit(factory,start,end,horizon):
    result={}
    active=None
    blocks=[]
    count=0
    def finish():
        if active is not None:result[active]=feature_month(np.concatenate(blocks))
    for batch in segment(factory,start,end):
        batch=batch[(batch[:,0]//60000).astype(np.int64)%horizon==0]
        # Split chronological batches at month boundaries; keep at most one month.
        labels=np.array([month_name(t) for t in batch[:,0]])
        for month in sorted(set(labels)):
            if active!=month:
                finish(); active=month; blocks=[]; count=0
            values=batch[labels==month,2:9]
            count+=len(values)
            if count>100000:raise ValueError('Monthly ranking memory cap exceeded')
            blocks.append(values)
    finish()
    return result


def run(paths,symbol,start,end,reserve_from,output,horizons=(15,60)):
    start_ms,end_ms,reserve_ms=map(timestamp,(start,end,reserve_from))
    shift_month(start,0);shift_month(end,0)
    if not start_ms<end_ms<=reserve_ms:raise ValueError('Require start < end <= reserved date')
    if not horizons or any(h not in (1,3,5,15,60) for h in horizons):raise ValueError('Unsupported horizon')
    output=Path(output)
    if output.exists():raise ValueError('Output exists; choose a new filename')
    paths=[Path(p).resolve() for p in paths]
    if not paths or len(set(paths))!=len(paths):raise ValueError('Supply unique chronological shards')
    sources=[]
    print('[audit] verifying provenance',flush=True)
    for path in paths:
        meta=json.loads(path.with_suffix('.json').read_text())
        if type(meta.get('last_open_ms')) is not int or meta['last_open_ms']>=reserve_ms:
            raise ValueError(f'Shard has missing range metadata or reaches reserved dates: {path.name}')
        digest=sha256(path)
        if (meta.get('sha256'),meta.get('venue'),meta.get('symbol'),meta.get('timeframe_ms'))!=(digest,'binance',symbol,60000):
            raise ValueError(f'Provenance mismatch: {path.name}')
        sources.append({'file':str(path),'sha256':digest})
    def guarded_rows():
        for row in candles(paths):
            if row['timestamp']>=reserve_ms:raise ValueError('Candle reaches reserved date despite metadata')
            yield row
    q=quality(guarded_rows(),start_ms,end_ms,lambda n:print(f'[audit] checked {n:,} rows',flush=True))
    per_horizon={}
    for h in horizons:
        print(f'[audit] feature ranking: horizon={h} minutes',flush=True)
        per_horizon[str(h)]=feature_audit(lambda:examples(paths,horizon=h),start_ms,end_ms,h)
    if any(sha256(p)!=s['sha256'] for p,s in zip(paths,sources)):raise ValueError('Inputs changed during audit')
    summary={'observed_minutes':sum(m['observed_minutes'] for m in q['monthly'].values()),
             'missing_minutes':sum(m['missing_minutes'] for m in q['monthly'].values()),
             'flags':{k:sum(m[k] for m in q['monthly'].values()) for k in
                      ('zero_volume','large_close_moves','large_open_jumps','volume_spikes')},'features_by_horizon':{}}
    for h,months in per_horizon.items():
        summary['features_by_horizon'][h]={}
        for feature in FEATURES:
            rhos=[m['features'][feature]['spearman'] for m in months.values()]
            rhos=[v for v in rhos if v is not None]
            summary['features_by_horizon'][h][feature]={'defined_months':len(rhos),
                'positive_months':sum(v>0 for v in rhos),'negative_months':sum(v<0 for v in rhos),
                'mean_spearman':float(np.mean(rhos)) if rhos else None}
    report={'approved':False,'pnl':None,'summary':summary,'quality':q,'feature_months':per_horizon,
        'spec':{'symbol':symbol,'start':start,'end':end,'reserve_from':reserve_from,'horizons':list(horizons),
                'sources':sources,'runner_sha256':sha256(Path(__file__))},
        'limitations':['Univariate association is not incremental model contribution, significance, or profitability.',
          'No OOD filter is applied; these samples differ from model-accepted ranking reports.',
          'Labels use a fixed non-overlapping UTC grid per horizon; serial dependence remains.',
          'Missing candles reset features; label boundaries are purged at the overall interval end.',
          'Months group by decision time; labels may cross internal month boundaries.',
          'Anomaly thresholds are fixed inspection heuristics, not proof of bad data. No records are modified.',
          'Checksums establish consistency with sidecars, not independent verification against the exchange.',
          'Development analysis only; no feature selection, model promotion or reserved-period evaluation.']}
    atomic_json(output,report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files',nargs='+',type=Path,required=True)
    p.add_argument('--symbol',required=True)
    p.add_argument('--start',required=True)
    p.add_argument('--end',required=True)
    p.add_argument('--reserve-from',required=True)
    p.add_argument('--horizons',nargs='+',type=int,default=[15,60])
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        report=run(a.files,a.symbol,a.start,a.end,a.reserve_from,a.output,a.horizons)
        print(json.dumps(report['summary'],indent=2))
        print(f'Completed: {a.output}; audit only, unapproved.')
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f'Audit stopped: {error}',file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('Interrupted; no complete report published.',file=sys.stderr);return 130


if __name__=='__main__':
    raise SystemExit(main())
