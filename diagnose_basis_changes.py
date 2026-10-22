"""Fixed-horizon, equal-quantity bid/ask change diagnostic; no executions."""
import argparse
from decimal import Decimal, localcontext
import json
from pathlib import Path

from audit_basis_quotes import audit
from engine_v1.dataset import sha256

HORIZONS = (5, 15, 30, 60)
LATENESS_NS = 250_000_000


def reference_changes(entry, exit):
    with localcontext() as ctx:
        ctx.prec = 40
        sb0, sa0, fb0, fa0 = [Decimal(entry[v][k]) for v,k in
                             [('spot','bid'),('spot','ask'),('usdm','bid'),('usdm','ask')]]
        sb1, sa1, fb1, fa1 = [Decimal(exit[v][k]) for v,k in
                             [('spot','bid'),('spot','ask'),('usdm','bid'),('usdm','ask')]]
        # Separate hypothetical one-ETH exposures on each leg; not actual fills.
        scale = Decimal(10000)/((sb0+sa0)/2)
        return {'long_futures_short_spot': (fb1-fa0+sb0-sa1)*scale,
                'long_spot_short_futures': (sb1-sa0+fb0-fa1)*scale}


def analyze(records, *, on_complete=None):
    anchors=[];active=None;next_anchor=None;last_time=-1;missed=0
    for record in records:
        if record['kind'] != 'receipt_pair': continue
        t=record['paired_monotonic_ns']
        if t<last_time: raise ValueError('Unordered pairs')
        last_time=t
        if active is not None:
            for horizon in HORIZONS:
                if horizon in active['labels']: continue
                target=active['entry']['paired_monotonic_ns']+horizon*1_000_000_000
                if t>=target:
                    active['labels'][horizon]=record if t-target<=LATENESS_NS else None
            if len(active['labels'])==len(HORIZONS): active=None
        if next_anchor is None: next_anchor=t
        if t>=next_anchor and active is None:
            # Skip missing grid slots; never backfill or choose on price.
            skipped=(t-next_anchor)//60_000_000_000
            missed+=skipped;next_anchor+=skipped*60_000_000_000
            if t-next_anchor<=LATENESS_NS:
                active={'entry':record,'labels':{}};anchors.append(active)
            else: missed+=1
            next_anchor+=60_000_000_000
    complete=[a for a in anchors if all(a['labels'].get(h) is not None for h in HORIZONS)]
    result={}
    for h in HORIZONS:
        sides={s:[] for s in ('long_futures_short_spot','long_spot_short_futures')}
        for a in complete:
            if on_complete is not None:
                on_complete(h, a['entry'], a['labels'][h])
            for side,value in reference_changes(a['entry'],a['labels'][h]).items():
                sides[side].append(value)
        result[str(h)]={s:dict(count=len(v),
            mean_reference_change_bps=str(sum(v)/len(v)) if v else None,
            min_reference_change_bps=str(min(v)) if v else None,
            max_reference_change_bps=str(max(v)) if v else None,
            positive_reference_changes=sum(x>0 for x in v)) for s,v in sides.items()}
    return dict(anchors_started=len(anchors),paired_complete_anchors=len(complete),
        incomplete_or_late_anchors=len(anchors)-len(complete),missed_anchor_slots=missed,
        horizons_seconds=result)


def diagnose(root):
    root=Path(root);verified=audit(root)
    def records():
        for name in verified['source_hashes']:
            if name.endswith('.jsonl'):
                with (root/name).open('rb') as handle:
                    for line in handle: yield json.loads(line)
    result=analyze(records())
    if any(sha256(root/p)!=h for p,h in verified['source_hashes'].items()):
        raise ValueError('Capture changed during analysis')
    return dict(approved=False,**result,source_hashes=verified['source_hashes'],
        runner_sha256=sha256(Path(__file__)),audit_runner_sha256=verified['runner_sha256'],
        replay_helpers_sha256=verified['replay_helpers_sha256'],
        protocol='60-second anchor grid; first valid pair within 250ms; labels at actual entry + horizon within 250ms; same complete anchors for all horizons',
        units='Arithmetic basis points of entry spot midpoint; equal one-ETH legs; not portfolio return',
        limitations=['Observed bid/ask references only; not synchronized executable prices or fills.',
            'Includes quoted spread crossings, excludes fees, slippage, funding, borrow and legging.',
            'Both directions are hypothetical; short spot requires inventory or borrowing.',
            'Five-minute pilot has very few complete anchors; no statistical or profitability claim.',
            'No parameter selection, trading, margin or liquidation model.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Use a new output path')
    result=diagnose(a.capture);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='source_hashes'},indent=2))


if __name__=='__main__': main()
