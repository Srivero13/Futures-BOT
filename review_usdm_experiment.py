"""Reconcile UM01 evidence and record failure without enabling promotion."""
import argparse
from decimal import Decimal,localcontext
import json
from pathlib import Path
from engine_v1.dataset import sha256
from usdm_sequence_accounting import decimal_string


FIELDS={'reference_price_pnl':'reference_price_pnl',
        'assumed_fees':'assumed_fees','assumed_price_impact_cost':'assumed_price_impact_cost',
        'funding_cashflow':'unambiguous_funding_cashflow','net_pnl':'scenario_net_pnl'}


def review(data):
    if data.get('experiment')!='UM01' or data.get('approved') is not False or data.get('status')!='development_only':
        raise ValueError('Expected an unapproved UM01 development report')
    ledger=data['ledger'];summary=data['summary'];trades=ledger['trades']
    if ledger.get('approved') is not False or ledger.get('accounting_reconciled') is not True:
        raise ValueError('Unresolved ledger')
    if len(trades)!=ledger['closed_trades'] or len(trades)!=summary['closed_trades']:
        raise ValueError('Trade count mismatch')
    with localcontext() as ctx:
        ctx.prec=50
        totals={k:Decimal(0) for k in FIELDS}
        sides={s:dict(trades=0,net=Decimal(0)) for s in ('long','short')}
        seen=set();profits=[]
        for trade in trades:
            if trade['id'] in seen:
                raise ValueError('Duplicate trade identity')
            seen.add(trade['id'])
            a=trade['accounting']
            if a.get('accounting_resolved_for_supplied_events') is not True:
                raise ValueError('Unresolved trade')
            values={k:decimal_string(a[v]) for k,v in FIELDS.items()}
            if min(values['assumed_fees'],values['assumed_price_impact_cost'])<0:
                raise ValueError('Negative costs unsupported')
            if values['net_pnl']!=values['reference_price_pnl']-values['assumed_fees']-values['assumed_price_impact_cost']+values['funding_cashflow']:
                raise ValueError('Trade components do not reconcile')
            for k,v in values.items(): totals[k]+=v
            if totals['net_pnl']!=decimal_string(trade['cumulative_realized_pnl']):
                raise ValueError('Cumulative realized P&L mismatch')
            q=decimal_string(a['quantity'])
            if q==0: raise ValueError('Zero quantity')
            side=sides['long' if q>0 else 'short']
            side['trades']+=1;side['net']+=values['net_pnl'];profits.append(values['net_pnl'])
        for k,v in totals.items():
            if v!=decimal_string(ledger[k]) or v!=decimal_string(summary[k]):
                raise ValueError('Summary component mismatch')
        for side in sides:
            if sides[side]['trades']!=summary[side+'_trades']:
                raise ValueError('Side count mismatch')
        without_best=totals['net_pnl']-max(profits) if profits else None
        if summary['net_pnl_excluding_best_trade']!=(str(without_best) if without_best is not None else None):
            # Decimal textual precision may differ in otherwise identical reports.
            if without_best is None or decimal_string(summary['net_pnl_excluding_best_trade'])!=without_best:
                raise ValueError('Best-trade sensitivity mismatch')
        gross_with_funding=totals['reference_price_pnl']+totals['funding_cashflow']
        reasons=[]
        if not profits: reasons.append('No completed trades')
        if totals['net_pnl']<=0: reasons.append('Nonpositive net P&L under stated assumptions')
        if gross_with_funding<=0: reasons.append('Nonpositive P&L even with zero fees and zero assumed price impact')
        return dict(approved=False,experiment='UM01',
            status='rejected_development' if reasons else 'requires_independent_validation',
            reasons=reasons,totals={k:str(v) for k,v in totals.items()},
            zero_fee_zero_impact_pnl=str(gross_with_funding),
            net_excluding_best_trade=None if without_best is None else str(without_best),
            sides={s:dict(trades=v['trades'],net_pnl=str(v['net'])) for s,v in sides.items()},
            note='Saved-accounting review only; no signal reconstruction, parameter selection or automatic promotion.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Output exists; choose a new path')
    digest=sha256(a.report);data=json.loads(a.report.read_text())
    hashes=data['inputs_sha256']
    if not hashes or any(sha256(k)!=v for k,v in hashes.items()): raise ValueError('Source inputs changed')
    r=review(data)
    if sha256(a.report)!=digest or any(sha256(k)!=v for k,v in hashes.items()): raise ValueError('Inputs changed during review')
    r.update(source_report_sha256=digest,runner_sha256=sha256(Path(__file__)))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))


if __name__=='__main__': main()
