"""Build fixed five-second research labels inside verified continuous book segments."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
import numpy as np
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from replay_market import replay
from walkforward_v16 import average_ranks,correlation


class Sampler:
    def __init__(self):
        self.pending=None;self.last=None;self.warm=None;self.segment=0
        self.rows=[];self.counts=Counter()

    def reset(self,reason):
        if self.pending is not None:self.counts['discarded_'+reason]+=1
        self.pending=None;self.last=None;self.warm=None;self.segment+=1

    def accept(self,record,quote):
        if quote is None:
            self.reset('boundary_or_uncovered');return
        t=record['receipt_monotonic_ns']
        if self.last is not None and t-self.last>1_000_000_000:
            self.reset('receipt_gap')
        self.last=t
        if self.warm is None:self.warm=t
        # Fixed warm-up after every boundary, not a guarantee of zero buffering.
        if t-self.warm<1_000_000_000:return
        bid,ask,bq,aq=map(float,quote);mid=(bid+ask)/2
        if not all(math.isfinite(v) and v>0 for v in (bid,ask,bq,aq)) or ask<=bid:
            raise ValueError('Invalid sampling quote')
        current={'decision_monotonic_ns':t,'decision_wall_ns':record['receipt_wall_ns'],
            'session':record['session'],'segment':self.segment,'mid':mid,
            'spread_bps':(ask-bid)/mid*10000,'quantity_imbalance':(bq-aq)/(bq+aq),
            'log_best_quantity':math.log(bq+aq)}
        if self.pending is not None:
            age=t-self.pending['decision_monotonic_ns']
            if age<5_000_000_000:return
            if age<=5_250_000_000:
                if len(self.rows)>=20000:raise ValueError('Sample cap exceeded')
                self.rows.append({**self.pending,'label_end_monotonic_ns':t,
                    'actual_horizon_ms':age/1e6,'target_mid_return_log_bps':math.log(mid/self.pending['mid'])*10000})
            else:self.counts['discarded_late_label']+=1
        # Consecutive labels share an endpoint, but never overlap.
        self.pending=current


def run(capture,output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    sampler=Sampler()
    try:
        verification=replay(capture,output/'replay-verification.json',on_quote=sampler.accept)
        sampler.reset('end_of_capture')
        if not sampler.rows:raise ValueError('No complete continuous samples')
        path=output/'samples.jsonl'
        with path.open('x') as f:
            for row in sampler.rows:f.write(json.dumps(row,allow_nan=False)+'\n')
        y=np.array([r['target_mid_return_log_bps'] for r in sampler.rows])
        x=np.array([r['quantity_imbalance'] for r in sampler.rows])
        summary={'samples':len(y),'horizon_seconds':5,'max_label_lateness_ms':250,
            'max_depth_receipt_gap_ms':1000,'warmup_ms':1000,'discarded':dict(sampler.counts),
            'mean_target_log_bps':float(y.mean()),'zero_rmse_log_bps':float(np.sqrt(np.mean(y*y))),
            'imbalance_spearman_descriptive':correlation(average_ranks(x),average_ranks(y)),
            'covered_depth_fraction':verification['covered_depth_fraction']}
        report={'approved':False,'pnl':None,'summary':summary,'samples_sha256':sha256(path),
            'capture':str(Path(capture).resolve()),'replay_sha256':sha256(output/'replay-verification.json'),
            'code_sha256':{p.name:sha256(p) for p in [Path(__file__),Path(__file__).parent/'replay_market.py',Path(__file__).parent/'record_market.py']},
            'limitations':['Descriptive development samples, not a fitted model or a holdout evaluation.',
            'Targets are midpoint changes over 5 to 5.25 seconds in application receipt time, not executable returns.',
            'Snapshot/connection boundaries, uncovered states, clock-jump flags and >1 second depth gaps reset sampling.',
            'A one-second warm-up does not establish source freshness or eliminate buffering.',
            'Selection excludes problematic intervals and is not representative of all market time.',
            'No transaction costs, slippage, queue position, confidence intervals or model approval.']}
        atomic_json(output/'summary.json',report)
        return summary
    except BaseException:
        # A completion manifest is the acceptance marker. Retain verification for diagnosis.
        (output/'samples.jsonl').unlink(missing_ok=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path)
    a=p.parse_args()
    try:
        print(json.dumps(run(a.capture,a.output_dir),indent=2))
        print(f'Completed: {a.output_dir}/summary.json; research-only, unapproved.')
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f'Microstructure build stopped: {error}',file=sys.stderr);return 2
    except KeyboardInterrupt:return 130
    return 0


if __name__=='__main__':raise SystemExit(main())
