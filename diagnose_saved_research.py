"""Summarize saved forecast buckets and error moments without retraining."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json


def finite(value):
    value=float(value)
    if not math.isfinite(value):raise ValueError('Non-finite report metric')
    return value


def diagnostic(ranking, expected_count):
    buckets=ranking['buckets']
    if not buckets:raise ValueError('Missing buckets')
    n=0;forecast_sum=actual_sum=0.
    for b in buckets:
        count=b['count']
        if type(count) is not int or count<0:raise ValueError('Invalid bucket count')
        if count:
            forecast_sum+=count*finite(b['mean_forecast_log_bps'])
            actual_sum+=count*finite(b['mean_actual_log_bps'])
        n+=count
    if n!=expected_count or n<=0:raise ValueError('Bucket counts disagree with test rows')
    mp,my=forecast_sum/n,actual_sum/n
    rmse=finite(ranking['rmse_log_bps']);zero=finite(ranking['zero_rmse_log_bps_same_rows'])
    if min(rmse,zero)<0:raise ValueError('Negative RMSE')
    mse=rmse**2;bias=mp-my;centered=mse-bias**2
    tolerance=1e-8*max(1,mse,zero**2)
    if centered < -tolerance or zero**2-my**2 < -tolerance:
        raise ValueError('Inconsistent report moments')
    # This is a retrospective mathematical decomposition, not a fitted correction.
    return {'rows':n,'rmse_log_bps':rmse,'zero_rmse_log_bps':zero,
        'excess_mse_vs_zero':mse-zero**2,'mean_forecast_log_bps':mp,
        'mean_actual_log_bps':my,'mean_error_log_bps':bias,
        'squared_mean_error_fraction_of_mse':bias**2/mse if mse else None,
        'centered_error_rmse_log_bps':math.sqrt(max(0,centered)),
        'actual_return_std_log_bps':math.sqrt(max(0,zero**2-my**2)),
        'top_bucket':buckets[-1],'bottom_bucket':buckets[0],
        'top_minus_bottom_actual_log_bps':ranking['top_minus_bottom_actual_log_bps'],
        'buckets':buckets}


def run(paths,output):
    output=Path(output)
    if output.exists():raise ValueError('Output exists; choose a new filename')
    paths=[Path(p).resolve() for p in paths]
    if not paths or len(paths)!=len(set(paths)):raise ValueError('Supply unique result files')
    fingerprints={};monthly=[];seen=set();groups={}
    for path in paths:
        digest=sha256(path);report=json.loads(path.read_text())
        # Glob patterns may include the launch and per-report protocols.
        if 'rankings' not in report:
            if 'summary' in report:raise ValueError('Unsupported summary report: '+str(path))
            continue
        fingerprints[str(path)]=digest
        protocol=report['protocol'];backend=protocol.get('backend','ridge')
        start=protocol['calibration_end_ms'];end=protocol['test_end_ms']
        test_month=datetime.fromtimestamp(start/1000,timezone.utc).strftime('%Y-%m')
        expected=report['summary']['paired_rows']['test']
        for model,r in report['rankings'].items():
            key=(protocol['symbol'],backend,model,start,end)
            if key in seen:raise ValueError('Duplicate backend/model/test interval')
            seen.add(key);d=diagnostic(r,expected)
            monthly.append({'symbol':protocol['symbol'],'backend':backend,'model':model,
                            'test_month':test_month,**d})
            groups.setdefault((protocol['symbol'],backend,model),[]).append(d)
    if not monthly:raise ValueError('No supported forecast reports found')
    summary=[]
    for (symbol,backend,model),rows in sorted(groups.items()):
        n=sum(r['rows'] for r in rows)
        mse=sum(r['rows']*r['rmse_log_bps']**2 for r in rows)/n
        zero=sum(r['rows']*r['zero_rmse_log_bps']**2 for r in rows)/n
        summary.append({'symbol':symbol,'backend':backend,'model':model,'folds':len(rows),'test_rows':n,
            'pooled_rmse_log_bps':math.sqrt(mse),'pooled_zero_rmse_log_bps':math.sqrt(zero),
            'folds_beating_zero':sum(r['excess_mse_vs_zero']<0 for r in rows),
            'positive_top_bucket_folds':sum(r['top_bucket']['count']>0 and r['top_bucket']['mean_actual_log_bps']>0 for r in rows),
            'defined_top_bucket_folds':sum(r['top_bucket']['count']>0 for r in rows)})
    if any(sha256(Path(p))!=h for p,h in fingerprints.items()):raise ValueError('Reports changed while reading')
    result={'approved':False,'pnl':None,'summary':summary,'monthly':monthly,'input_sha256':fingerprints,
        'runner_sha256':sha256(Path(__file__)),
        'limitations':['Saved bucket aggregates cannot reconstruct daily errors, tails, individual predictions or confidence intervals.',
        'Centered error removes the test-set mean error algebraically; it is not an out-of-sample correction or deployable result.',
        'Bucket returns are before costs and not executable P&L. No bucket is selected for trading.',
        'Pooled RMSE weights squared errors by row count; folds are retrospective development periods, not independent tests.']}
    atomic_json(output,result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reports',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        report=run(a.reports,a.output)
        print(json.dumps(report['summary'],indent=2))
        print('\nMONTHLY BIAS AND TOP BUCKET (log-bps before costs):')
        for r in report['monthly']:
            b=r['top_bucket']
            print(f"{r['test_month']} {r['backend']} {r['model']} | bias={r['mean_error_log_bps']:.5f} | top_n={b['count']} top_return={b['mean_actual_log_bps']} | top-bottom={r['top_minus_bottom_actual_log_bps']}")
        print(f'Completed: {a.output}; diagnostic only, unapproved.')
    except (ValueError,OSError,KeyError,TypeError,OverflowError) as error:
        print(f'Saved diagnostic stopped: {error}',file=sys.stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
