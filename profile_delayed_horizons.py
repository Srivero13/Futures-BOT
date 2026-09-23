"""Fixed paired holding-period study of frozen signals; retrospective research only."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from build_delayed_microstructure import Sampler as BaseSampler
from diagnose_delayed_execution import cost_barrier
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from replay_market import replay
from train_delayed_microstructure import FEATURES, SETTINGS, predict
from walkforward_v16 import average_ranks, correlation

HORIZONS=(5,15,30,60)


class Sampler(BaseSampler):
    def __init__(self,model):
        super().__init__();self.model=model
        cuts=model['training_forecast_bucket_cuts']
        if not cuts or not math.isfinite(float(cuts[-1])):raise ValueError('Invalid frozen cutoff')
        self.cutoff=float(cuts[-1])

    def accept(self,r,q):
        if q is None:self.reset('boundary_or_uncovered');return
        if r['receipt_wall_ns']<=self.model['frozen_at_wall_ns']:raise ValueError('Capture precedes model freeze')
        t=r['receipt_monotonic_ns']
        if self.last is not None and t-self.last>1_000_000_000:self.reset('receipt_gap')
        self.last=t
        if self.warm is None:self.warm=t
        if t-self.warm<1_000_000_000:return
        bid,ask,bq,aq=map(float,q);mid=(bid+ask)/2
        if not all(math.isfinite(v) and v>0 for v in (bid,ask,bq,aq)) or ask<=bid:raise ValueError('Invalid quote')
        if self.pending is not None:
            p=self.pending
            if 'entry_ns' not in p:
                age=t-p['decision_ns']
                if age<500_000_000:return
                if age<=750_000_000:
                    p['entry_ns']=t;p['entry_ask']=ask;return
                self.counts['discarded_late_entry']+=1;self.pending=None
            else:
                horizon=HORIZONS[len(p['targets'])];age=t-p['entry_ns']
                if age<horizon*1_000_000_000:return
                if age>horizon*1_000_000_000+250_000_000:
                    self.counts['discarded_late_label']+=1;self.pending=None
                else:
                    p['targets'][str(horizon)]={'end_ns':t,'exit_bid':bid,'quote_return_log_bps':math.log(bid/p['entry_ask'])*10000}
                    if len(p['targets'])<len(HORIZONS):return
                    if len(self.rows)>=20000:raise ValueError('Sample cap exceeded')
                    self.rows.append(p);self.pending=None
        features=[(ask-bid)/mid*10000,(bq-aq)/(bq+aq),math.log(bq+aq)]
        score=float(predict(np.array([features]),self.model)[0])
        if not math.isfinite(score):raise ValueError('Non-finite frozen score')
        self.pending={'decision_ns':t,'decision_wall_ns':r['receipt_wall_ns'],'session':r['session'],
            'segment':self.segment,'features':features,'frozen_five_second_score':score,
            'selected':score>0 and score>=self.cutoff,'targets':{}}
        self.counts['anchors_started']+=1


def summarize(sampler):
    rows=sampler.rows
    if not rows:raise ValueError('No complete paired samples')
    selected=np.array([r['selected'] for r in rows],dtype=bool)
    scores=np.array([r['frozen_five_second_score'] for r in rows]);barrier=cost_barrier()
    horizons={}
    for h in HORIZONS:
        y=np.array([r['targets'][str(h)]['quote_return_log_bps'] for r in rows]);top=y[selected]
        horizons[str(h)]={'paired_samples':len(y),'selected_samples':len(top),
            'mean_quote_return_log_bps':float(y.mean()),
            'selected_mean_quote_return_log_bps':float(top.mean()) if len(top) else None,
            'selected_mean_minus_cost_barrier_log_bps':float(top.mean()-barrier) if len(top) else None,
            'selected_realized_returns_above_cost_barrier':int(np.sum(top>barrier)),
            'frozen_score_spearman_descriptive':correlation(average_ranks(scores),average_ranks(y))}
    return {'paired_samples':len(rows),'selected_samples':int(selected.sum()),'discarded':dict(sampler.counts),
            'frozen_cutoff_log_bps':sampler.cutoff,'cost_barrier_log_bps':barrier,'horizons':horizons}


def run(capture,model_path,output):
    capture=Path(capture).resolve();model_path=Path(model_path);output=Path(output);root=Path(__file__).parent
    if output.exists():raise ValueError('Output exists; choose a new directory')
    digest=sha256(model_path);m=json.loads(model_path.read_text())
    if m['kind']!='delayed_microstructure_research_ridge' or m['features']!=FEATURES or m['settings']!=SETTINGS or m['alpha']!=10:
        raise ValueError('Unsupported delayed model')
    if m['runner_sha256']!=sha256(root/'train_delayed_microstructure.py'):raise ValueError('Training code changed')
    if str(capture)==m['training']['capture']:raise ValueError('Use a separate capture')
    for name,expected in m['training']['builder_code_sha256'].items():
        if Path(name).name!=name or sha256(root/name)!=expected:raise ValueError('Sampling code changed')
    training=json.loads((Path(m['training']['capture'])/'protocol.json').read_text())
    current=json.loads((capture/'protocol.json').read_text())
    if training['symbol']!=current['symbol']:raise ValueError('Symbols differ')
    sampler=Sampler(m);output.mkdir(parents=True)
    replay(capture,output/'replay-verification.json',on_quote=sampler.accept)
    sampler.reset('end_of_capture');summary=summarize(sampler)
    if sha256(model_path)!=digest:raise ValueError('Model changed')
    samples=output/'paired-samples.jsonl'
    with samples.open('x') as f:
        for row in sampler.rows:f.write(json.dumps(row,allow_nan=False)+'\n')
    atomic_json(output/'summary.json',{'approved':False,'pnl':None,'summary':summary,'model_sha256':digest,
        'samples_sha256':sha256(samples),'replay_sha256':sha256(output/'replay-verification.json'),
        'code_sha256':{n:sha256(root/n) for n in ('profile_delayed_horizons.py','build_delayed_microstructure.py','diagnose_delayed_execution.py','diagnose_execution_microstructure.py','train_delayed_microstructure.py','replay_market.py','record_market.py')},
        'limitations':['Retrospective exploratory horizon study on already inspected data; not new validation or horizon selection.',
        'Frozen five-second model used only as a signal score, not as a calibrated forecast for longer horizons.',
        'Identical entries across horizons; complete cases only. Any failed horizon discards the entire anchor.',
        'Anchors do not overlap across their full 60-second window. Boundaries reset sampling and reduce representativeness.',
        'Fee/slippage barrier is a hypothetical constant; margins are log-return diagnostics, not cash P&L.',
        'No fill/size checks, exit latency, queue model, uncertainty intervals or portfolio accounting.',
        'All four horizons are reported without picking a winner; any revised strategy needs fresh frozen validation.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','model','output-dir'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    try:print(json.dumps(run(a.capture,a.model,a.output_dir),indent=2))
    except (ValueError,OSError,KeyError,TypeError) as e:p.exit(2,f'Horizon study stopped: {e}\n')


if __name__=='__main__':main()
