"""Retrospective paired block-bootstrap diagnostics; never model approval."""
import argparse
import json
from pathlib import Path
import tempfile
import numpy as np
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from train_delayed_microstructure import load_dataset, fit_arrays, predict, evaluate


def summarize(y, prediction, baseline, selected, times):
    """Resample five-minute wall-clock clusters, retaining paired predictions."""
    arrays=[np.asarray(a) for a in (y,prediction,baseline,selected,times)]
    y,prediction,baseline,selected,times=arrays
    if not len(y) or any(a.shape!=y.shape for a in arrays):raise ValueError('Invalid paired arrays')
    if not all(np.isfinite(a).all() for a in arrays):raise ValueError('Non-finite arrays')
    if np.any(np.diff(times)<0):raise ValueError('Wall time regressed')
    groups=(times-times[0])//300_000_000_000
    blocks=[]
    for group in np.unique(groups):
        mask=groups==group;top=mask & selected.astype(bool)
        blocks.append([mask.sum(),np.sum((prediction[mask]-y[mask])**2),np.sum((baseline[mask]-y[mask])**2),
                       np.sum(y[mask]**2),top.sum(),y[top].sum()])
    b=np.asarray(blocks,dtype=float)
    if len(b)<3:raise ValueError('Require at least three occupied five-minute blocks')
    def metrics(t):
        n,model,base,zero,count,total=t
        return [np.sqrt(model/n)-np.sqrt(zero/n),np.sqrt(model/n)-np.sqrt(base/n),total/count if count else np.nan]
    point=metrics(b.sum(0));rng=np.random.default_rng(1729)
    draws=np.array([metrics(b[rng.integers(0,len(b),len(b))].sum(0)) for _ in range(2000)])
    keys=['model_minus_zero_rmse_log_bps','model_minus_imbalance_rmse_log_bps','frozen_top_bucket_mean_quote_log_bps']
    result={}
    for i,key in enumerate(keys):
        valid=draws[:,i][np.isfinite(draws[:,i])]
        result[key]={'estimate':float(point[i]) if np.isfinite(point[i]) else None,
                     'percentile_95_interval':np.quantile(valid,[.025,.975]).tolist() if len(valid)>=1900 else None,
                     'defined_replicates':len(valid)}
    return {'samples':len(y),'occupied_blocks':len(b),'block_seconds':300,'replicates':2000,'seed':1729,
            'selected_samples':int(np.sum(selected)),'metrics':result}


def run(training,dataset,model,output):
    training,dataset,model,output=map(Path,(training,dataset,model,output))
    if output.exists():raise ValueError('Output exists; choose a new filename')
    digest=sha256(model);m=json.loads(model.read_text())
    # Reuse all frozen-model, timing, sampling-code and integrity gates.
    with tempfile.TemporaryDirectory() as temp:
        evaluate(dataset,model,Path(temp)/'validation.json')
    tx,ty,provenance=load_dataset(training)
    if provenance!=m['training']:raise ValueError('Training dataset differs from frozen model provenance')
    x,y,source=load_dataset(dataset)
    weights=fit_arrays(tx[:,1:2],ty)
    p=predict(x,m);baseline=predict(x[:,1:2],weights)
    cuts=m['training_forecast_bucket_cuts']
    if not cuts:raise ValueError('Frozen model has no defined bucket cuts')
    selected=p>=cuts[-1]
    rows=[json.loads(line) for line in (dataset/'samples.jsonl').read_text().splitlines()]
    if sha256(dataset/'samples.jsonl')!=source['samples_sha256']:raise ValueError('Dataset changed')
    summary=summarize(y,p,baseline,selected,np.array([r['decision_wall_ns'] for r in rows],dtype=np.int64))
    if sha256(model)!=digest:raise ValueError('Model changed')
    atomic_json(output,{'approved':False,'pnl':None,'summary':summary,'model_sha256':digest,
        'training':provenance,'evaluation':source,'imbalance_baseline_weights':weights,'runner_sha256':sha256(Path(__file__)),
        'limitations':['Retrospective diagnostic on an already examined forward recording; not a new holdout.',
        'Imbalance-only ridge uses original training rows and alpha 10; introduced after inspecting prior results.',
        'Five-minute occupied wall-time blocks resampled as paired clusters; block length is fixed, not optimized.',
        'Intervals are conditional on this recording and frozen models; dependence beyond blocks and nonstationarity may invalidate coverage.',
        'Unequal block sizes are retained; empty time intervals are not imputed. No training-estimation uncertainty.',
        'Top bucket uses unchanged training cuts, after observed spread but before fees, extra slippage and fill/size checks.',
        'No strategy selection, complete execution result, significance claim, or live approval.']})
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('training','dataset','model','output'):parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args()
    try:print(json.dumps(run(a.training,a.dataset,a.model,a.output),indent=2))
    except (ValueError,OSError,KeyError,TypeError) as error:parser.exit(2,f'Diagnostic stopped: {error}\n')


if __name__=='__main__':main()
