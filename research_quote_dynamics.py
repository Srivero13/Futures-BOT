"""Paired retrospective feature ablation on separate chronological recordings."""
import argparse
import json
from pathlib import Path
import numpy as np
from build_quote_dynamics import DYNAMIC_FEATURES,run as build
from train_delayed_microstructure import load_dataset,fit_arrays,predict
from walkforward_v16 import average_ranks,correlation
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json


def load(root):
    x,y,p=load_dataset(root)
    report=json.loads((root/'summary.json').read_text())
    if report['summary'].get('feature_set')!='best_quote_dynamics_v1':raise ValueError('Wrong feature set')
    rows=[json.loads(line) for line in (root/'samples.jsonl').read_text().splitlines()]
    extra=np.array([[r[k] for k in DYNAMIC_FEATURES] for r in rows])
    if not np.isfinite(extra).all() or len(extra)!=len(y):raise ValueError('Invalid dynamics')
    if sha256(root/'samples.jsonl')!=p['samples_sha256']:raise ValueError('Dataset changed')
    return x,np.column_stack((x,extra)),y,p


def compare(training,evaluation,output):
    if output.exists():raise ValueError('Report exists')
    tx,trich,ty,tp=load(training);x,rich,y,ep=load(evaluation)
    if tp['capture']==ep['capture'] or ep['first_decision_wall_ns']<=tp['last_label_wall_ns_estimate']:
        raise ValueError('Require separate later evaluation capture')
    if tp['builder_code_sha256']!=ep['builder_code_sha256']:raise ValueError('Builder mismatch')
    metrics={};models={}
    for name,a,b in [('three_features',tx,x),('plus_quote_dynamics',trich,rich)]:
        model=fit_arrays(a,ty);p=predict(b,model);train_predictions=predict(a,model)
        threshold=float(np.quantile(train_predictions,.8));selected=(p>=threshold)&(p>0)
        metrics[name]={'rmse_log_bps':float(np.sqrt(np.mean((p-y)**2))),
            'spearman':correlation(average_ranks(p),average_ranks(y)),
            'training_top_cutoff_log_bps':threshold,'selected_samples':int(selected.sum()),
            'selected_mean_quote_log_bps':float(y[selected].mean()) if selected.any() else None}
        models[name]=model
    summary={'training_samples':len(ty),'evaluation_samples':len(y),'zero_rmse_log_bps':float(np.sqrt(np.mean(y*y))),
        'models':metrics,'dynamic_minus_base_rmse_log_bps':metrics['plus_quote_dynamics']['rmse_log_bps']-metrics['three_features']['rmse_log_bps']}
    atomic_json(output,{'approved':False,'pnl':None,'summary':summary,'training':tp,'evaluation':ep,
        'weights_for_reproducibility_only':models,'extra_features':DYNAMIC_FEATURES,'alpha':10,'runner_sha256':sha256(Path(__file__)),
        'limitations':['Retrospective ablation on previously inspected recordings; not a new forward test.',
        'Both models refitted on identical original-training-capture rows, with training-only normalization and cutoffs.',
        'Extra features are past best-quote changes, not full book depth or aggressive trade flow.',
        'Labels include spread but exclude fees, extra slippage, fill size and portfolio accounting.',
        'No hyperparameter search, uncertainty claim, frozen production model or approval.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('training-capture','evaluation-capture','output-dir'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    try:
        if a.output_dir.exists():raise ValueError('Output directory exists; choose a new one')
        training_protocol=json.loads((a.training_capture/'protocol.json').read_text())
        evaluation_protocol=json.loads((a.evaluation_capture/'protocol.json').read_text())
        if training_protocol['symbol']!=evaluation_protocol['symbol']:raise ValueError('Capture symbols differ')
        a.output_dir.mkdir(parents=True)
        print('[dynamics] building training recording',flush=True);build(a.training_capture,a.output_dir/'training')
        print('[dynamics] building evaluation recording',flush=True);build(a.evaluation_capture,a.output_dir/'evaluation')
        print('[dynamics] fitting paired CPU models',flush=True)
        print(json.dumps(compare(a.output_dir/'training',a.output_dir/'evaluation',a.output_dir/'report.json'),indent=2))
    except (ValueError,OSError,KeyError,TypeError) as e:p.exit(2,f'Dynamics research stopped: {e}\n')


if __name__=='__main__':main()
