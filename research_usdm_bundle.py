"""Unchanged UM01 rule on the August 8–31 development bundle; no promotion."""
import argparse
from datetime import date,timedelta
from decimal import Decimal,localcontext
import json
from pathlib import Path
from audit_usdm_pilot import audit as audit_trades
from audit_usdm_funding import audit as audit_funding
from batch_usdm_marks import audit_marks
from download_usdm_funding import timestamp
from engine_v1.dataset import candles,sha256
from research_usdm_momentum import plan
from usdm_sequence_accounting import account_sequence


def load_bundle(root):
    root=Path(root);manifest=root/'bundle.json';digest=sha256(manifest)
    m=json.loads(manifest.read_text());identity=m['identity']
    start,end,reserve=date(2026,8,8),date(2026,9,1),date(2026,9,1)
    expected=dict(symbol='ETHUSDT',start=str(start),end_exclusive=str(end),reserve_from=str(reserve),format_version=1)
    days=[start+timedelta(days=i) for i in range(24)]
    if m.get('approved') is not False or m.get('status')!='complete' or m.get('minutes')!=34560 or any(identity.get(k)!=v for k,v in expected.items()) or m.get('completed_days')!=list(map(str,days)):
        raise ValueError('Expected a complete August 8–31 ETHUSDT bundle')
    hashes=m['inputs_sha256']
    if not hashes or any(sha256(p)!=h for p,h in hashes.items()): raise ValueError('Bundle input changed')
    audited={}
    def retain(a):
        for p,h in a['inputs_sha256'].items():
            if hashes.get(p)!=h: raise ValueError('Reaudit differs from completed bundle')
            audited[p]=h
    rows=[];marks=[];events=[];chunks=[]
    spot=Path(identity['spot_root'])/'binance-ETHUSDT-2026-08.csv'
    for i,day in enumerate(days,1):
        print(f'[UM01-bundle] verifying day {i}/24: {day}',flush=True)
        folder=root/'trades'/str(day)
        a=audit_trades(folder,spot,'ETHUSDT',day,reserve)
        if a.get('matched_minutes')!=1440 or a.get('integrity_passed') is not True: raise ValueError('Trade audit failed')
        retain(a);rows.extend(candles([folder/f'binance-usdm-ETHUSDT-{day}.csv']))
        folder=root/'marks'/str(day)
        a=audit_marks(folder,day);retain(a)
        marks.extend(json.loads((folder/'marks.json').read_text()))
    cursor=start
    while cursor<end:
        stop=min(cursor+timedelta(days=7),end);folder=root/'funding'/str(cursor)
        a=audit_funding(folder,'ETHUSDT',cursor,stop,reserve);retain(a)
        chunk=json.loads((folder/'funding.json').read_text());events.extend(chunk)
        chunks.append(dict(start=str(cursor),end_exclusive=str(stop),records=len(chunk)));cursor=stop
    if chunks!=m['funding_chunks'] or audited!=hashes:
        raise ValueError('Bundle audit coverage differs from manifest')
    hashes=dict(hashes);hashes[str(manifest.resolve())]=digest
    return rows,marks,events,hashes


def weekly_summary(ledger):
    start=date(2026,8,8);end=date(2026,9,1);result=[]
    with localcontext() as ctx:
        ctx.prec=50
        while start<end:
            stop=min(start+timedelta(days=7),end)
            selected=[t['accounting'] for t in ledger['trades'] if timestamp(start)<=t['accounting']['exit_ms']<timestamp(stop)]
            result.append(dict(start=str(start),end_exclusive=str(stop),closed_trades=len(selected),
                               net_pnl=str(sum((Decimal(t['scenario_net_pnl']) for t in selected),Decimal(0)))))
            start=stop
        if sum((Decimal(r['net_pnl']) for r in result),Decimal(0))!=Decimal(ledger['net_pnl']):
            raise ValueError('Exit-week totals do not reconcile')
    return result


def run(root):
    rows,marks,events,hashes=load_bundle(root)
    trades,unclosed=plan(rows)
    print(f'[UM01-bundle] accounting {len(trades)} trades',flush=True)
    ledger=account_sequence(trades,marks,events,'5','2')
    weeks=weekly_summary(ledger)
    with localcontext() as ctx:
        ctx.prec=50
        profits=[Decimal(t['accounting']['scenario_net_pnl']) for t in ledger['trades']]
        without_best=str(Decimal(ledger['net_pnl'])-max(profits)) if profits else None
    summary={k:ledger[k] for k in ('closed_trades','net_pnl','reference_price_pnl','assumed_fees',
        'assumed_price_impact_cost','funding_cashflow','max_sampled_drawdown_quote','accounting_reconciled')}
    summary.update(long_trades=sum(Decimal(t['quantity'])>0 for t in trades),short_trades=sum(Decimal(t['quantity'])<0 for t in trades),
                   boundary_candidates_not_evaluated=unclosed,net_pnl_excluding_best_trade=without_best,exit_week_totals=weeks)
    if any(sha256(p)!=h for p,h in hashes.items()): raise ValueError('Inputs changed during evaluation')
    code={name:sha256(Path(__file__).parent/name) for name in ('research_usdm_bundle.py','research_usdm_momentum.py',
         'usdm_sequence_accounting.py','diagnose_usdm_roundtrip.py','diagnose_usdm_mark_path.py','funding_cashflows.py')}
    return dict(approved=False,experiment='UM01',status='development_only',period='2026-08-08 through 2026-08-31',
                summary=summary,ledger=ledger,trade_plan=trades,inputs_sha256=hashes,code_sha256=code,
                original_rejection_preserved=True,limitations=[
                'Unchanged rule on additional development data; not independent strategy validation.',
                'First 60 minutes supply warmup; earlier August 7 candles are not loaded.',
                'Weekly totals assign full trade P&L to exit week, not mark-to-market weekly returns; positions are not reset.',
                'No parameter search or promotion. Original August 1–7 failure remains part of the evidence.',
                'Hypothetical costs and reference fills; no margin, liquidation or funding-completeness guarantee.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Output exists; choose a new path')
    r=run(a.bundle);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r['summary'],indent=2))
    print(f'Completed: {a.output}; development-only, unapproved.')


if __name__=='__main__': main()
