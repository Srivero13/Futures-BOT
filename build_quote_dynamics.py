"""Build causal best-quote dynamics with unchanged delayed-return labels."""
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


from collections import deque
from build_delayed_microstructure import Sampler as DelayedSampler

DYNAMIC_FEATURES=['mid_return_1s','imbalance_change_1s','log_quantity_change_1s','spread_change_1s','mid_return_5s']


class Sampler(DelayedSampler):
    def __init__(self):
        super().__init__();self.history=deque()

    def reset(self,reason):
        super().reset(reason);self.history.clear()

    def accept(self,r,q):
        if q is None:self.reset('boundary_or_uncovered');return
        t=r['receipt_monotonic_ns']
        if self.history and t-self.history[-1][0]>1_000_000_000:self.reset('receipt_gap')
        bid,ask,bq,aq=map(float,q);mid=(bid+ask)/2
        if not all(math.isfinite(v) and v>0 for v in (bid,ask,bq,aq)) or ask<=bid:raise ValueError('Invalid quote')
        now=(t,mid,(bq-aq)/(bq+aq),math.log(bq+aq),(ask-bid)/mid*10000)
        self.history.append(now)
        # Retain the last observation at/before five seconds ago, plus newer ones.
        while len(self.history)>1 and self.history[1][0]<=t-5_000_000_000:self.history.popleft()
        if len(self.history)>100000:raise ValueError('Quote history cap exceeded')
        if t-self.history[0][0]<5_000_000_000:return
        one=next(v for v in reversed(self.history) if v[0]<=t-1_000_000_000)
        five=self.history[0]
        super().accept(r,q)
        if self.pending is not None and self.pending['decision_monotonic_ns']==t:
            self.pending.update(dict(zip(DYNAMIC_FEATURES,[math.log(mid/one[1])*10000,
                now[2]-one[2],now[3]-one[3],now[4]-one[4],math.log(mid/five[1])*10000])))
            self.pending['lag_1s_actual_ms']=(t-one[0])/1e6
            self.pending['lag_5s_actual_ms']=(t-five[0])/1e6



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
        y=np.array([r['target_quote_return_log_bps'] for r in sampler.rows])
        x=np.array([r['quantity_imbalance'] for r in sampler.rows])
        summary={'feature_set':'best_quote_dynamics_v1','history_seconds':5,'samples':len(y),'horizon_seconds':5,'entry_delay_ms':500,'max_entry_lateness_ms':250,'target':'delayed_ask_to_bid_log_bps','max_label_lateness_ms':250,
            'max_depth_receipt_gap_ms':1000,'warmup_ms':1000,'discarded':dict(sampler.counts),
            'mean_target_log_bps':float(y.mean()),'zero_rmse_log_bps':float(np.sqrt(np.mean(y*y))),
            'imbalance_spearman_descriptive':correlation(average_ranks(x),average_ranks(y)),
            'covered_depth_fraction':verification['covered_depth_fraction']}
        report={'approved':False,'pnl':None,'summary':summary,'samples_sha256':sha256(path),
            'capture':str(Path(capture).resolve()),'replay_sha256':sha256(output/'replay-verification.json'),
            'code_sha256':{p.name:sha256(p) for p in [Path(__file__),Path(__file__).parent/'build_delayed_microstructure.py',Path(__file__).parent/'replay_market.py',Path(__file__).parent/'record_market.py']},
            'limitations':['Descriptive development samples, not a fitted model or a holdout evaluation.',
            'Targets use the first ask 500 to 750 ms after decision and first bid 5 to 5.25 seconds after entry; receipt time only.',
            'Snapshot/connection boundaries, uncovered states, clock-jump flags and >1 second depth gaps reset sampling.',
            'Five seconds of causal quote history plus inherited one-second warm-up; no freshness guarantee.',
            'Lag features use last quote at or before lag time; receipt gaps bounded to one second. These are best-quote dynamics, not aggressive trade flow.',
            'Selection excludes problematic intervals and is not representative of all market time.',
            'Observed spread is included; fees, extra slippage, size, queue position and fill guarantees are not. No model approval.']}
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
