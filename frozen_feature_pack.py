"""Freeze three fixed feature models and compare them on later captures."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from research_quote_dynamics import load as load_dynamics
from research_aggressive_flow import load as load_flow
from build_quote_dynamics import run as build_dynamics,DYNAMIC_FEATURES
from build_aggressive_flow import run as build_flow,FLOW_FEATURES
from train_delayed_microstructure import fit_arrays,predict,FEATURES
from diagnose_delayed_execution import cost_barrier
from walkforward_v16 import average_ranks,correlation

FILES=('frozen_feature_pack.py','research_quote_dynamics.py','research_aggressive_flow.py',
       'build_quote_dynamics.py','build_aggressive_flow.py','build_delayed_microstructure.py',
       'train_delayed_microstructure.py','replay_market.py','record_market.py',
       'diagnose_delayed_execution.py','diagnose_execution_microstructure.py','walkforward_v16.py',
       'engine_v1/dataset.py','engine_v1/operations.py')
FEATURE_SETS={'baseline':FEATURES,'quote_dynamics':FEATURES+DYNAMIC_FEATURES,'aggressive_flow':FEATURES+FLOW_FEATURES}


def code_hashes():
    return {name:sha256(Path(__file__).parent/name) for name in FILES}


def paired(dynamics,flow):
    dbase,dx,dy,dp=load_dynamics(dynamics);fbase,fx,fy,fp=load_flow(flow)
    if dp['capture']!=fp['capture']:raise ValueError('Feature datasets must use the same capture')
    def keys(root,source):
        rows=[json.loads(line) for line in (root/'samples.jsonl').read_text().splitlines()]
        if sha256(root/'samples.jsonl')!=source['samples_sha256']:raise ValueError('Samples changed')
        result=[(r['decision_monotonic_ns'],r['entry_monotonic_ns'],r['label_end_monotonic_ns']) for r in rows]
        if len(set(result))!=len(result):raise ValueError('Duplicate sample keys')
        return result
    dk=keys(dynamics,dp);fk=keys(flow,fp);lookup={k:i for i,k in enumerate(fk)}
    di=np.array([i for i,k in enumerate(dk) if k in lookup],dtype=int)
    fi=np.array([lookup[dk[i]] for i in di],dtype=int)
    if len(di)<100:raise ValueError('Require at least 100 common timing-aligned rows')
    if not np.array_equal(dy[di],fy[fi]) or not np.array_equal(dbase[di],fbase[fi]):raise ValueError('Paired labels/features differ')
    return {'baseline':dbase[di],'quote_dynamics':dx[di],'aggressive_flow':fx[fi]},dy[di],{'dynamics':dp,'flow':fp}, {'dynamics_rows':len(dy),'flow_rows':len(fy),'common_rows':len(di)}


def freeze(dynamics,flow,output):
    if output.exists():raise ValueError('Pack exists; do not overwrite a frozen pack')
    x,y,source,counts=paired(dynamics,flow);models={}
    current=code_hashes()
    for provenance in source.values():
        for name,digest in provenance['builder_code_sha256'].items():
            if name not in current or current[name]!=digest:raise ValueError('Builder code differs from training provenance')
    capture=Path(source['flow']['capture']);symbol=json.loads((capture/'protocol.json').read_text())['symbol']
    for name,a in x.items():
        weights=fit_arrays(a,y);p=predict(a,weights)
        models[name]={'weights':weights,'top_cutoff':float(np.quantile(p,.8)),'features':FEATURE_SETS[name]}
    pack={'kind':'frozen_feature_pack_v1','approved':False,'alpha':10,'symbol':symbol,
          'models':models,'training':source,'training_counts':counts,'code_sha256':current,
          'frozen_at_wall_ns':time.time_ns(),'cost_barrier_log_bps':cost_barrier()}
    atomic_json(output,pack)
    return {'pack':str(output),'training_counts':counts,'models':list(models),'frozen_at_wall_ns':pack['frozen_at_wall_ns'],'approved':False}


def evaluate(capture,pack_path,output):
    if output.exists():raise ValueError('Output exists; choose a new directory')
    digest=sha256(pack_path);pack=json.loads(pack_path.read_text())
    if pack['kind']!='frozen_feature_pack_v1' or pack['alpha']!=10 or set(pack['models'])!=set(FEATURE_SETS):raise ValueError('Unsupported pack')
    if pack['code_sha256']!=code_hashes():raise ValueError('Code changed since freeze; use the frozen code version')
    if json.loads((capture/'protocol.json').read_text())['symbol']!=pack['symbol']:raise ValueError('Capture symbol differs')
    # Inspect first raw receipt before doing expensive replay; hash verification follows.
    with (capture/'events-00000.jsonl').open() as handle:raw=json.loads(handle.readline())
    if raw['receipt_wall_ns']<=pack['frozen_at_wall_ns']:raise ValueError('Capture must start after pack freeze')
    output.mkdir(parents=True)
    print('[pack] building quote dynamics',flush=True);build_dynamics(capture,output/'dynamics')
    print('[pack] building aggressive flow',flush=True);build_flow(capture,output/'flow')
    x,y,source,counts=paired(output/'dynamics',output/'flow')
    for key,p in source.items():
        training=pack['training'][key]
        if p['capture']==training['capture'] or p['first_decision_wall_ns']<=max(pack['frozen_at_wall_ns'],training['last_label_wall_ns_estimate']):raise ValueError('Evaluation is not later independent data')
        if p['builder_code_sha256']!=training['builder_code_sha256']:raise ValueError('Builder provenance differs')
    metrics={}
    for name,a in x.items():
        m=pack['models'][name]
        if m['features']!=FEATURE_SETS[name]:raise ValueError('Feature order differs')
        p=predict(a,m['weights'])
        if not np.isfinite(p).all():raise ValueError('Non-finite predictions')
        selected=(p>0)&(p>=m['top_cutoff']);eligible=selected&(p>=pack['cost_barrier_log_bps'])
        metrics[name]={'rmse_log_bps':float(np.sqrt(np.mean((p-y)**2))),
            'spearman':correlation(average_ranks(p),average_ranks(y)),
            'selected_samples':int(selected.sum()),'selected_mean_quote_log_bps':float(y[selected].mean()) if selected.any() else None,
            'cost_eligible_forecasts':int(eligible.sum()),'frozen_top_cutoff_log_bps':m['top_cutoff']}
    if sha256(pack_path)!=digest:raise ValueError('Pack changed during evaluation')
    summary={'counts':counts,'zero_rmse_log_bps':float(np.sqrt(np.mean(y*y))),'models':metrics}
    atomic_json(output/'report.json',{'approved':False,'pnl':None,'summary':summary,'pack_sha256':digest,'evaluation':source,
        'limitations':['Three fixed models evaluated without fitting or cutoff changes; no automatic winner selection.',
        'Only identical decision/entry/exit samples common to both builders are compared; omitted intervals may bias results.',
        'Local clock ordering and hashes enforce chronology, not proof of unseen data or source freshness.',
        'Quote returns include spread but omit fees, additional slippage, fill size and portfolio accounting.',
        'Cost eligibility is a forecast screen under fixed assumptions, not a trade or a profit guarantee.',
        'A single capture does not establish performance across days; retain the same pack for subsequent captures.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze')
    for name in ('dynamics-training','flow-training','output'):f.add_argument('--'+name,required=True,type=Path)
    e=sub.add_parser('evaluate')
    for name in ('capture','pack','output-dir'):e.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    try:
        result=freeze(a.dynamics_training,a.flow_training,a.output) if a.command=='freeze' else evaluate(a.capture,a.pack,a.output_dir)
        print(json.dumps(result,indent=2))
    except (ValueError,OSError,KeyError,TypeError) as error:p.exit(2,f'Frozen pack stopped: {error}\n')


if __name__=='__main__':main()
