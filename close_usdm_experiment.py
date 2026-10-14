"""Combine the two UM01 development runs without double-counting trades."""
import argparse
from datetime import date
from decimal import Decimal,localcontext
import json
from pathlib import Path
from download_usdm_funding import timestamp
from engine_v1.dataset import sha256
from review_usdm_experiment import review,FIELDS


def combine(first,extension):
    if any(d.get('experiment')!='UM01' for d in (first,extension)):
        raise ValueError('UM01 closure cannot mix experiments')
    reports=(first,extension)
    windows=((date(2026,8,1),date(2026,8,8)),(date(2026,8,8),date(2026,9,1)))
    reviews=[];seen=set();profits=[];counts=0;boundary=0
    with localcontext() as ctx:
        ctx.prec=50
        totals={k:Decimal(0) for k in FIELDS}
        for data,(start,end) in zip(reports,windows):
            checked=review(data);reviews.append(checked)
            previous=None
            for trade in data['ledger']['trades']:
                a=trade['accounting'];entry,exit_time=a['entry_ms'],a['exit_ms']
                if trade['id'] in seen: raise ValueError('Duplicate trade across reports')
                seen.add(trade['id'])
                if any(type(t) is not int for t in (entry,exit_time)) or not timestamp(start)<=entry<exit_time<timestamp(end):
                    raise ValueError('Trade outside expected development window')
                if previous is not None and entry<=previous: raise ValueError('Overlapping or unordered trades')
                previous=exit_time;profits.append(Decimal(a['scenario_net_pnl']))
            counts+=len(data['ledger']['trades'])
            omitted=data['summary']['boundary_candidates_not_evaluated']
            if type(omitted) is not int or omitted<0: raise ValueError('Invalid boundary count')
            boundary+=omitted
            for k in totals: totals[k]+=Decimal(checked['totals'][k])
        rejected=totals['net_pnl']<=0 or any(r['status']=='rejected_development' for r in reviews)
        return dict(approved=False,experiment='UM01',status='closed_rejected_development' if rejected else 'unapproved_requires_independent_validation',
            evaluated_runs=2,closed_trades=counts,boundary_candidates_not_evaluated=boundary,
            totals={k:str(v) for k,v in totals.items()},
            zero_fee_zero_impact_pnl=str(totals['reference_price_pnl']+totals['funding_cashflow']),
            net_excluding_best_trade=str(totals['net_pnl']-max(profits)) if profits else None,
            run_reviews=reviews,limitations=[
                'Sum of two separately evaluated runs, not a reconstructed continuous August portfolio.',
                'Each run has its own warmup and end-boundary exclusions; global drawdown is not inferred or added.',
                'Saved accounting and period checks only; no independent signal or fill reconstruction.',
                'Preserves failed development evidence. No parameter tuning, signal inversion or promotion.'])


def run(paths):
    if len(paths)!=2 or Path(paths[0]).resolve()==Path(paths[1]).resolve(): raise ValueError('Two distinct source reports required')
    hashes={};reports=[]
    for path in paths:
        path=Path(path);hashes[str(path.resolve())]=sha256(path)
        data=json.loads(path.read_text());sources=data['inputs_sha256']
        if not sources: raise ValueError('Missing source provenance')
        for p,h in sources.items():
            if p in hashes and hashes[p]!=h: raise ValueError('Inconsistent shared source hashes')
            if sha256(p)!=h: raise ValueError('Changed source input')
            hashes[p]=h
        reports.append(data)
    result=combine(*reports)
    if any(sha256(p)!=h for p,h in hashes.items()): raise ValueError('Inputs changed during closure')
    result.update(inputs_sha256=hashes,runner_sha256=sha256(Path(__file__)))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--first-report',type=Path,required=True)
    p.add_argument('--extension-report',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Output exists; choose a new path')
    r=run([a.first_report,a.extension_report]);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('inputs_sha256','run_reviews')},indent=2))


if __name__=='__main__': main()
