"""Frozen delayed-entry quote-return ridge research; no live approval."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from walkforward_v16 import average_ranks,correlation

FEATURES=['spread_bps','quantity_imbalance','log_best_quantity']
SETTINGS={'horizon_seconds':5,'entry_delay_ms':500,'max_entry_lateness_ms':250,'target':'delayed_ask_to_bid_log_bps','max_label_lateness_ms':250,'max_depth_receipt_gap_ms':1000,'warmup_ms':1000}


def load_dataset(root):
    root=Path(root);manifest=root/'summary.json';path=root/'samples.jsonl'
    mh=sha256(manifest);report=json.loads(manifest.read_text());digest=sha256(path)
    if digest!=report['samples_sha256']:raise ValueError('Sample checksum mismatch')
    if any(report['summary'][k]!=v for k,v in SETTINGS.items()):raise ValueError('Unsupported sampling settings')
    verification=root/'replay-verification.json'
    if sha256(verification)!=report['replay_sha256']:raise ValueError('Replay verification checksum mismatch')
    if not json.loads(verification.read_text())['integrity_passed']:raise ValueError('Replay did not pass')
    rows=[];last_end=None
    with path.open() as f:
        for line in f:
            r=json.loads(line);start=r['decision_monotonic_ns'];end=r['label_end_monotonic_ns']
            entry=r['entry_monotonic_ns']
            if (not 500_000_000<=entry-start<=750_000_000 or not 5_000_000_000<=end-entry<=5_250_000_000
                    or (last_end is not None and start<last_end)):
                raise ValueError('Overlapping or invalid labels')
            last_end=end;rows.append(r)
            if len(rows)>20000:raise ValueError('Sample cap exceeded')
    if len(rows)!=report['summary']['samples'] or len(rows)<100:raise ValueError('Require >=100 consistent samples')
    x=np.array([[r[k] for k in FEATURES] for r in rows]);y=np.array([r['target_quote_return_log_bps'] for r in rows])
    if not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Non-finite samples')
    if sha256(path)!=digest or sha256(manifest)!=mh:raise ValueError('Dataset changed while loading')
    provenance={'capture':report['capture'],'samples_sha256':digest,'manifest_sha256':mh,
        'builder_code_sha256':report['code_sha256'],
        'first_decision_wall_ns':min(r['decision_wall_ns'] for r in rows),
        'last_label_wall_ns_estimate':max(r['decision_wall_ns']+r['label_end_monotonic_ns']-r['decision_monotonic_ns'] for r in rows)}
    return x,y,provenance


def fit_arrays(x,y):
    mean=x.mean(0);scale=x.std(0);scale[scale<1e-12]=1
    a=np.column_stack((np.ones(len(x)),(x-mean)/scale))
    penalty=np.eye(a.shape[1])*np.sqrt(10.);penalty[0,0]=0
    coef=np.linalg.lstsq(np.vstack((a,penalty)),np.r_[y,np.zeros(a.shape[1])],rcond=None)[0]
    return {'mean':mean.tolist(),'scale':scale.tolist(),'coefficients':coef.tolist()}


def predict(x,model):
    return np.column_stack((np.ones(len(x)),(x-np.array(model['mean']))/np.array(model['scale'])))@np.array(model['coefficients'])


def fit(root,output):
    if Path(output).exists():raise ValueError('Model exists; choose another filename')
    x,y,source=load_dataset(root);weights=fit_arrays(x,y)
    forecasts=predict(x,weights)
    model={'kind':'delayed_microstructure_research_ridge','approved':False,'features':FEATURES,'settings':SETTINGS,'alpha':10,
        **weights,'training':source,'training_rows':len(y),'frozen_at_wall_ns':time.time_ns(),
        'training_forecast_bucket_cuts':np.unique(np.quantile(forecasts,[.2,.4,.6,.8])).tolist() if np.ptp(forecasts)>0 else [],
        'runner_sha256':sha256(Path(__file__)),
        'note':'Development fit only; no training score is evidence of generalization. No live loader or trading approval.'}
    atomic_json(Path(output),model)
    return {'training_rows':len(y),'frozen_at_wall_ns':time.time_ns(),'features':FEATURES,'alpha':10,'approved':False,'model':str(output)}


def evaluate(root,model_path,output):
    if Path(output).exists():raise ValueError('Evaluation exists; choose another filename')
    model_path=Path(model_path);digest=sha256(model_path);m=json.loads(model_path.read_text())
    if m['kind']!='delayed_microstructure_research_ridge' or m['features']!=FEATURES or m['settings']!=SETTINGS or m['alpha']!=10:
        raise ValueError('Unsupported research model')
    if m['runner_sha256']!=sha256(Path(__file__)):raise ValueError('Runner changed since model fit')
    x,y,source=load_dataset(root);training=m['training']
    if source['capture']==training['capture'] or source['samples_sha256']==training['samples_sha256']:
        raise ValueError('Evaluation must use a separate recording')
    if source['first_decision_wall_ns']<=training['last_label_wall_ns_estimate']:
        raise ValueError('Evaluation recording must be later than development labels')
    if source['first_decision_wall_ns']<=m['frozen_at_wall_ns']:
        raise ValueError('Evaluation samples must be recorded after the model was frozen')
    if source['builder_code_sha256']!=training['builder_code_sha256']:raise ValueError('Sampling code differs between datasets')
    p=predict(x,m)
    if not np.isfinite(p).all():raise ValueError('Non-finite forecasts')
    ids=np.searchsorted(m['training_forecast_bucket_cuts'],p,side='right');buckets=[]
    for i in range(len(m['training_forecast_bucket_cuts'])+1):
        mask=ids==i
        buckets.append({'bucket':i+1,'count':int(mask.sum()),'mean_forecast_log_bps':float(p[mask].mean()) if mask.any() else None,
            'mean_actual_quote_log_bps_before_fees_slippage':float(y[mask].mean()) if mask.any() else None})
    summary={'samples':len(y),'model_rmse_log_bps':float(np.sqrt(np.mean((p-y)**2))),
        'zero_rmse_log_bps':float(np.sqrt(np.mean(y*y))),
        'forecast_spearman':correlation(average_ranks(p),average_ranks(y)),
        'imbalance_spearman':correlation(average_ranks(x[:,1]),average_ranks(y)),
        'mean_error_log_bps':float(np.mean(p-y)),'buckets':buckets}
    if sha256(model_path)!=digest:raise ValueError('Model changed during evaluation')
    atomic_json(Path(output),{'approved':False,'pnl':None,'summary':summary,'model_sha256':digest,'evaluation':source,
        'limitations':['Later recording is enforced by dataset identity and local wall-clock ordering, not proof of never inspected data.',
        'Wall-clock label end is estimated using monotonic elapsed time; clock flags already filter samples.',
        'Training-only normalization and bucket cuts. No fitting or parameter selection on evaluation data.',
        'Delayed ask-to-bid forecast diagnostics include spread but not fees, extra slippage or size checks. Not execution P&L; serial dependence and selection remain.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('fit','evaluate'):
        s=sub.add_parser(name);s.add_argument('--dataset',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
        if name=='evaluate':s.add_argument('--model',type=Path,required=True)
    a=p.parse_args()
    try:
        result=fit(a.dataset,a.output) if a.command=='fit' else evaluate(a.dataset,a.model,a.output)
        print(json.dumps(result,indent=2));print('Completed; research-only, unapproved.')
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f'Microstructure research stopped: {error}',file=sys.stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
