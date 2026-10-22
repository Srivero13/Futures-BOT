"""Apply explicit hypothetical costs to the fixed basis quote anchors."""
import argparse
from decimal import Decimal, localcontext
import json
from pathlib import Path

from audit_basis_quotes import audit
from basis_cost_accounting import account, number
from diagnose_basis_changes import analyze, HORIZONS
from engine_v1.dataset import sha256

SIDES=('long_futures_short_spot','long_spot_short_futures')


def validate_costs(spot_fee, futures_fee, slippage):
    for name,value in [('spot fee',spot_fee),('futures fee',futures_fee),('slippage',slippage)]:
        if number(value,name)>=10000:
            raise ValueError('Rates must be below 10000 bps')


def costed_changes(entry, exit, spot_fee, futures_fee, slippage):
    result={}
    for side in SIDES:
        scenario=dict(quantity_eth='1',direction=side,cost_source='Explicit hypothetical CLI rates; not verified account fees')
        for venue,source,fee in [('spot','spot',spot_fee),('futures','usdm',futures_fee)]:
            scenario[venue]=dict(fee_bps_per_execution=fee,slippage_bps_per_execution=slippage,
                entry={k:entry[source][k] for k in ('bid','ask')},
                exit={k:exit[source][k] for k in ('bid','ask')})
        result[side]=Decimal(account(scenario)['subtotal_bps_of_entry_spot_notional'])
    return result


def cost_summary(records, spot_fee, futures_fee, slippage):
    validate_costs(spot_fee,futures_fee,slippage)
    values={str(h):{s:[] for s in SIDES} for h in HORIZONS}
    def collect(h,entry,exit):
        for side,value in costed_changes(entry,exit,spot_fee,futures_fee,slippage).items():
            values[str(h)][side].append(value)
    reference=analyze(records,on_complete=collect)
    summary={}
    with localcontext() as ctx:
        ctx.prec=50
        for h,sides in values.items():
            summary[h]={s:dict(count=len(v),
                mean_subtotal_bps=str(sum(v)/len(v)) if v else None,
                min_subtotal_bps=str(min(v)) if v else None,
                max_subtotal_bps=str(max(v)) if v else None,
                positive_subtotals=sum(x>0 for x in v)) for s,v in sides.items()}
    return dict(reference_diagnostic=reference,cost_scenario_horizons_seconds=summary)


def diagnose(root,spot_fee,futures_fee,slippage):
    validate_costs(spot_fee,futures_fee,slippage)
    root=Path(root);verified=audit(root)
    def records():
        for name in verified['source_hashes']:
            if name.endswith('.jsonl'):
                with (root/name).open('rb') as f:
                    for line in f: yield json.loads(line)
    result=cost_summary(records(),spot_fee,futures_fee,slippage)
    if any(sha256(root/p)!=h for p,h in verified['source_hashes'].items()):
        raise ValueError('Capture changed during cost analysis')
    return dict(approved=False,**result,
        assumptions=dict(spot_fee_bps_per_execution=spot_fee,futures_fee_bps_per_execution=futures_fee,
                         slippage_bps_per_execution=slippage,source='Hypothetical; not account-verified'),
        source_hashes=verified['source_hashes'],runner_sha256=sha256(Path(__file__)),
        accounting_sha256=sha256(Path(__file__).with_name('basis_cost_accounting.py')),
        anchor_runner_sha256=sha256(Path(__file__).with_name('diagnose_basis_changes.py')),
        audit_runner_sha256=verified['runner_sha256'],replay_helpers_sha256=verified['replay_helpers_sha256'],
        limitations=['Same complete fixed anchors for all horizons; no price-based or cost-based selection.',
            'Subtotal before funding, financing and borrow; not executable P&L.',
            'Asynchronous quotes, no fill, inventory, margin or liquidation model.',
            'Arithmetic bps of entry spot notional; one ETH per leg, not portfolio return.',
            'Hypothetical cost sensitivity of a tiny pilot; no strategy approval.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--spot-fee-bps',required=True);p.add_argument('--futures-fee-bps',required=True)
    p.add_argument('--slippage-bps',required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Use a new output path')
    result=diagnose(a.capture,a.spot_fee_bps,a.futures_fee_bps,a.slippage_bps)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_hashes','reference_diagnostic')},indent=2))


if __name__=='__main__': main()
