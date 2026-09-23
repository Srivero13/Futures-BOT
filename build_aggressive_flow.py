"""Build causal receipt-ordered aggressive flow with delayed-return labels."""
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
import hashlib
from build_delayed_microstructure import Sampler as DelayedSampler

FLOW_FEATURES=['taker_imbalance_1s','taker_imbalance_5s','log_agg_rate_5s','flow_book_interaction']


def records(capture):
    for part in json.loads((capture/'summary.json').read_text())['parts']:
        name=part['file']
        if Path(name).name!=name:raise ValueError('Invalid part path')
        digest=hashlib.sha256();size=0
        with (capture/name).open('rb') as f:
            for raw in f:
                digest.update(raw);size+=len(raw)
                yield json.loads(raw)
        if size!=part['bytes'] or digest.hexdigest()!=part['sha256']:raise ValueError('Flow input checksum mismatch')


class FlowCursor:
    def __init__(self,source):
        self.source=iter(source);self.previous=None;self.events=deque();self.last_id=None;self.generation=0

    def clear(self):
        self.events.clear()

    def advance(self,target):
        if self.previous==target:return
        for r in self.source:
            if r==target:
                self.previous=r;return
            if r.get('clock_jump') or r['kind'] in ('session_start','session_error','snapshot','snapshot_refresh','unexpected_event'):
                self.clear();self.last_id=None;self.generation+=1
            if r['kind']=='aggTrade' and not r.get('clock_jump'):
                d=r['data'];ident=int(d['a'])
                if self.last_id is not None and ident!=self.last_id+1:
                    self.clear();self.generation+=1
                if self.last_id is not None and ident<=self.last_id:continue
                self.last_id=ident
                if type(d['m']) is not bool:raise ValueError('Invalid maker flag')
                price,qty=float(d['p']),float(d['q']);amount=price*qty
                if not all(math.isfinite(v) and v>0 for v in (price,qty,amount)):raise ValueError('Invalid trade amount')
                t=r['receipt_monotonic_ns']
                self.events.append((t,amount,-amount if d['m'] else amount));self.prune(t)
                if len(self.events)>100000:raise ValueError('Flow window cap exceeded')
        raise ValueError('Quote record not found in flow source')

    def prune(self,t):
        while self.events and self.events[0][0]<=t-5_000_000_000:self.events.popleft()

    def features(self,t,book_imbalance):
        self.prune(t)
        recent=[e for e in self.events if e[0]>t-1_000_000_000]
        def ratio(events):
            total=sum(e[1] for e in events)
            return sum(e[2] for e in events)/total if total else 0.
        five=ratio(self.events)
        return [ratio(recent),five,math.log1p(len(self.events)/5),five*book_imbalance]

    def finish(self):
        for _ in self.source:pass


class Sampler(DelayedSampler):
    def __init__(self,cursor):
        super().__init__();self.cursor=cursor;self.flow_warm=None;self.generation=cursor.generation;self.quote_last=None

    def reset(self,reason):
        super().reset(reason);self.cursor.clear();self.flow_warm=None;self.quote_last=None

    def accept(self,r,q):
        self.cursor.advance(r)
        if self.cursor.generation!=self.generation:
            self.reset('flow_boundary_or_id_gap');self.generation=self.cursor.generation
        if q is None:self.reset('boundary_or_uncovered');return
        t=r['receipt_monotonic_ns']
        if self.quote_last is not None and t-self.quote_last>1_000_000_000:self.reset('receipt_gap')
        self.quote_last=t
        if self.flow_warm is None:self.flow_warm=t
        if t-self.flow_warm<5_000_000_000:return
        super().accept(r,q)
        if self.pending is not None and self.pending['decision_monotonic_ns']==t:
            self.pending.update(dict(zip(FLOW_FEATURES,self.cursor.features(t,self.pending['quantity_imbalance']))))



def run(capture,output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    cursor=FlowCursor(records(Path(capture)));sampler=Sampler(cursor)
    try:
        verification=replay(capture,output/'replay-verification.json',on_quote=sampler.accept)
        cursor.finish();sampler.reset('end_of_capture')
        if not sampler.rows:raise ValueError('No complete continuous samples')
        path=output/'samples.jsonl'
        with path.open('x') as f:
            for row in sampler.rows:f.write(json.dumps(row,allow_nan=False)+'\n')
        y=np.array([r['target_quote_return_log_bps'] for r in sampler.rows])
        x=np.array([r['quantity_imbalance'] for r in sampler.rows])
        summary={'feature_set':'aggressive_flow_v1','history_seconds':5,'samples':len(y),'horizon_seconds':5,'entry_delay_ms':500,'max_entry_lateness_ms':250,'target':'delayed_ask_to_bid_log_bps','max_label_lateness_ms':250,
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
            'Five seconds of flow warm-up plus inherited one-second warm-up; no freshness guarantee.',
            'Flow uses earlier records only, including receipt timestamp ties in file order. Buyer-maker means sell aggressor. No backfill; aggregate-ID gaps reset sampling.',
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
