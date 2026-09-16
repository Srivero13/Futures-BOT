"""Expanding-window historical research with calibration-defined forecast buckets."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(name, '1')

import numpy as np
from engine_v1.dataset import examples, segment, sha256
from engine_v1.fast import FastPredictor
from engine_v1.nonlinear import PolynomialModel, load_model
from engine_v1.operations import atomic_json
from train_v15 import timestamp
from train_v16 import run_training

MAX_RANK_ROWS = 100000


def shift_month(date, offset):
    value = datetime.strptime(date, '%Y-%m-%d')
    if value.day != 1:
        raise ValueError('Use first-of-month dates')
    index = value.year*12+value.month-1+offset
    year, month = divmod(index,12)
    return datetime(year,month+1,1,tzinfo=timezone.utc).strftime('%Y-%m-%d')


def folds(first_test, months):
    if type(months) is not int or not 1 <= months <= 24:
        raise ValueError('Use 1..24 test months')
    return [{'train_end':shift_month(first_test,i-1),
             'calibration_end':shift_month(first_test,i),
             'test_end':shift_month(first_test,i+1)} for i in range(months)]


def average_ranks(values):
    """One-based average ranks; equal predictions never get arbitrary ordering."""
    order = np.argsort(values, kind='stable')
    sorted_values = values[order]
    boundaries = np.r_[0, np.flatnonzero(np.diff(sorted_values) != 0)+1, len(values)]
    result = np.empty(len(values),dtype=float)
    for left,right in zip(boundaries[:-1],boundaries[1:]):
        result[order[left:right]] = (left+1+right)/2
    return result


def correlation(a,b):
    if len(a) < 2:
        return None
    a,b = a-a.mean(),b-b.mean()
    denominator = float(np.linalg.norm(a)*np.linalg.norm(b))
    return float(np.dot(a,b)/denominator) if denominator else None


def collect(factory, model, start, end):
    predictor = model if isinstance(model,PolynomialModel) else FastPredictor(model)
    blocks = []
    accepted = total = 0
    for batch in segment(factory,start,end):
        # Fixed UTC grid prevents overlapping return intervals; gaps cannot shift phase.
        batch = batch[(batch[:,0]//60000).astype(np.int64) % model.horizon_bars == 0]
        total += len(batch)
        p = predictor.batch(batch[:,2:8])
        valid = np.isfinite(p)
        accepted += int(np.sum(valid))
        if accepted > MAX_RANK_ROWS:
            raise ValueError('Ranking row cap exceeded; shorten evaluation interval')
        blocks.append(np.column_stack((p[valid],batch[valid,8])))
    result = np.concatenate(blocks) if blocks else np.empty((0,2))
    return result, {'grid_examples':total,'accepted':accepted,'ood_rejected':total-accepted}


def ranking(calibration, test):
    for rows in (calibration,test):
        if rows.ndim != 2 or rows.shape[1] != 2 or not np.isfinite(rows).all():
            raise ValueError('Expected finite forecast/return pairs')
    if len(calibration) < 30 or len(test) < 30:
        raise ValueError('Require at least 30 accepted calibration and test grid examples')
    # Cuts depend exclusively on calibration forecasts, never test returns/forecasts.
    cuts = (np.unique(np.quantile(calibration[:,0],[.2,.4,.6,.8]))
            if np.ptp(calibration[:,0]) > 0 else np.empty(0))
    p,y = test[:,0],test[:,1]
    ids = np.searchsorted(cuts,p,side='right')
    buckets = []
    for i in range(len(cuts)+1):
        selected = ids == i
        buckets.append({'bucket':i+1,'count':int(np.sum(selected)),
                        'lower_inclusive':float(cuts[i-1]) if i else None,
                        'upper_exclusive':float(cuts[i]) if i < len(cuts) else None,
                        'mean_forecast_log_bps':float(p[selected].mean()) if selected.any() else None,
                        'mean_actual_log_bps':float(y[selected].mean()) if selected.any() else None})
    bottom,top = buckets[0]['mean_actual_log_bps'],buckets[-1]['mean_actual_log_bps']
    spread = top-bottom if len(buckets)>1 and top is not None and bottom is not None else None
    return {'calibration_forecast_cuts_log_bps':cuts.tolist(),
            'spearman':correlation(average_ranks(p),average_ranks(y)),
            'pearson':correlation(p,y), 'buckets':buckets,
            'top_minus_bottom_actual_log_bps':spread,
            'rmse_log_bps':float(np.sqrt(np.mean((p-y)**2))),
            'zero_rmse_log_bps_same_rows':float(np.sqrt(np.mean(y*y))),
            'note':'Descriptive ranking on a fixed non-overlapping UTC grid; serial dependence can remain. No significance claim or P&L.'}


def run(paths, symbol, first_test, months, work_dir, output, model_kind='linear', horizon=3, alpha=10.):
    schedule = folds(first_test,months)
    output = Path(output)
    if output.exists():
        raise ValueError('Output exists; choose a new filename')
    paths = [Path(p).resolve() for p in paths]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError('Supply unique chronological shards')
    sources = [{'file':str(p),'sha256':sha256(p)} for p in paths]
    results = []
    print('[walk-forward] fixed schedule: '+json.dumps(schedule),flush=True)
    for index,fold in enumerate(schedule,1):
        print(f'[walk-forward] fold {index}/{months}: test {fold["calibration_end"]} to {fold["test_end"]}',flush=True)
        # Existing guarded trainer checks source identity, purges boundary labels,
        # fits scaling only on the training prefix and saves resumable artifacts.
        directory, training = run_training(paths,'binance',symbol,work_dir,
            timestamp(fold['train_end']),timestamp(fold['calibration_end']),timestamp(fold['test_end']),
            model_kind=model_kind,horizon=horizon,alpha=alpha)
        model = load_model(directory/'model.json')
        factory = lambda:examples(paths,horizon=horizon)
        calibration,cal_counts = collect(factory,model,timestamp(fold['train_end']),timestamp(fold['calibration_end']))
        test,test_counts = collect(factory,model,timestamp(fold['calibration_end']),timestamp(fold['test_end']))
        result = {'fold':index,**fold,'model_directory':str(directory),
                  'model_sha256':sha256(directory/'model.json'),
                  'calibration_counts':cal_counts,'test_counts':test_counts,
                  'ranking':ranking(calibration,test),
                  'overlapping_forecast_diagnostics':training['holdout']}
        results.append(result)
        print('[walk-forward] ranking: '+json.dumps({k:v for k,v in result['ranking'].items() if k not in ('buckets','note')}),flush=True)
    if any(sha256(p) != s['sha256'] for p,s in zip(paths,sources)):
        raise ValueError('Sources changed during walk-forward evaluation')
    rhos = [r['ranking']['spearman'] for r in results if r['ranking']['spearman'] is not None]
    spreads = [r['ranking']['top_minus_bottom_actual_log_bps'] for r in results
               if r['ranking']['top_minus_bottom_actual_log_bps'] is not None]
    report = {'approved':False,'pnl':None,'symbol':symbol,'venue':'binance',
        'model_kind':model_kind,'horizon':horizon,'alpha':alpha,'folds':results,'sources':sources,
        'code_sha256':{str(p):sha256(p) for p in [Path(__file__),Path(__file__).parent/'train_v16.py',
              *[Path(__file__).parent/'engine_v1'/f for f in ('dataset.py','training.py','model.py','nonlinear.py','fast.py')]]},
        'summary':{'folds':len(results),'defined_spearman_folds':len(rhos),
                   'positive_spearman_folds':sum(r>0 for r in rhos),
                   'mean_fold_spearman':float(np.mean(rhos)) if rhos else None,
                   'defined_bucket_spread_folds':len(spreads),'positive_bucket_spread_folds':sum(s>0 for s in spreads)},
        'limitations':['Retrospective expanding-window research, not independent untouched holdouts or a promotion criterion.',
          'Training uses all supplied history before each cutoff; prior test months enter later training windows.',
          'One month calibrates each fold; test returns never determine forecast bucket thresholds.',
          'Fixed UTC-grid labels do not overlap, but market serial dependence remains. No confidence intervals or p-values.',
          'Quantile cut ties are collapsed; empty test buckets yield null metrics. Constant forecasts have undefined rank correlation.',
          'Buckets are descriptive, not tradable strategies; no transaction costs or fills are applied to bucket means.',
          'Training holdout diagnostics use overlapping labels and their existing cost screen; ranking uses a different subset.',
          'Gaps reset features and may reduce coverage; counts are reported but uninterrupted data is not certified.',
          'No automatic parameter search, best-model selection, retraining loop or approval.']}
    atomic_json(output,report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files',nargs='+',type=Path,required=True)
    parser.add_argument('--symbol',required=True)
    parser.add_argument('--first-test',required=True)
    parser.add_argument('--months',type=int,default=6)
    parser.add_argument('--model',choices=['linear','polynomial'],default='linear')
    parser.add_argument('--horizon',type=int,choices=[1,3,5],default=3)
    parser.add_argument('--alpha',type=float,default=10.)
    parser.add_argument('--work-dir',type=Path,default=Path('data/walkforward-models'))
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        report = run(args.files,args.symbol,args.first_test,args.months,args.work_dir,args.output,
                     args.model,args.horizon,args.alpha)
        print(json.dumps(report['summary'],indent=2))
        print(f'Completed: {args.output}; research-only, unapproved.')
        return 0
    except KeyboardInterrupt:
        print('Interrupted; rerun to reuse completed fits. No aggregate report published.',file=sys.stderr)
        return 130
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as error:
        print(f'Walk-forward stopped: {error}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
