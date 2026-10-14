"""Fixed-time futures accounting scenario, not a strategy or fill backtest."""
import argparse
from datetime import date
from decimal import Decimal, localcontext
import json
from pathlib import Path
from diagnose_usdm_exposure import run as verify_week
from download_usdm_funding import timestamp
from engine_v1.dataset import candles, sha256
from funding_cashflows import funding_cashflow, event_exposure


def roundtrip(quantity, entry_price, exit_price, entry_ms, exit_ms, events, fee_bps, impact_bps):
    with localcontext() as ctx:
        ctx.prec=50
        q,p0,p1,fee,impact=map(Decimal,(quantity,entry_price,exit_price,fee_bps,impact_bps))
        if not all(x.is_finite() for x in (q,p0,p1,fee,impact)) or q==0 or min(p0,p1)<=0:
            raise ValueError('Invalid position/prices')
        if not (0<=fee<10000 and 0<=impact<10000):
            raise ValueError('Invalid cost assumptions')
        event_exposure(entry_ms,exit_ms,entry_ms)
        direction=Decimal(1) if q>0 else Decimal(-1)
        entry_fill=p0*(1+direction*impact/10000)
        exit_fill=p1*(1-direction*impact/10000)
        reference=q*(p1-p0)
        execution=q*(exit_fill-entry_fill)
        fees=abs(q)*(entry_fill+exit_fill)*fee/10000
        funding=Decimal(0)
        held=outside=0
        ambiguous=[]
        last=None
        for event in events:
            t=event['funding_time_ms']
            if type(t) is not int or (last is not None and t<=last):
                raise ValueError('Funding times must be unique and ordered')
            last=t
            exposure=event_exposure(entry_ms,exit_ms,t)
            if exposure=='ambiguous':
                ambiguous.append(t)
            elif exposure=='held':
                funding+=funding_cashflow(str(q),event['mark_price'],event['funding_rate'])
                held+=1
            else:
                outside+=1
        return dict(quantity=str(q),entry_ms=entry_ms,exit_ms=exit_ms,
                    entry_fill_assumption=str(entry_fill),exit_fill_assumption=str(exit_fill),
                    reference_price_pnl=str(reference),assumed_price_impact_cost=str(reference-execution),
                    assumed_fees=str(fees),unambiguous_funding_cashflow=str(funding),
                    held_funding_events=held,outside_funding_events=outside,
                    ambiguous_funding_times_ms=ambiguous,
                    scenario_net_pnl=None if ambiguous else str(execution-fees+funding),
                    funding_boundary_guard_ms=60000,
                    accounting_resolved_for_supplied_events=not ambiguous)


def run(first,batch,spot,funding,fee,impact):
    verified=verify_week(first,batch,spot,funding)
    entry=timestamp(date(2026,8,1))+120000
    exit_time=timestamp(date(2026,8,8))-120000
    def price(folder,day,t):
        for row in candles([Path(folder)/f'binance-usdm-ETHUSDT-{day}.csv']):
            if row['timestamp']==t:
                return row['open']
        raise ValueError('Missing fixed-time reference candle')
    p0=price(first,'2026-08-01',entry)
    p1=price(Path(batch)/'2026-08-07','2026-08-07',exit_time)
    events=json.loads((Path(funding)/'funding.json').read_text())
    scenarios={side:roundtrip(q,p0,p1,entry,exit_time,events,fee,impact)
               for side,q in [('long_one_eth','1'),('short_one_eth','-1')]}
    if any(sha256(p)!=h for p,h in verified['inputs_sha256'].items()):
        raise ValueError('Inputs changed during scenario calculation')
    return dict(approved=False,symbol='ETHUSDT',
                scenario='Fixed entry August 1 00:02 UTC; exit August 7 23:58 UTC; one ETH',
                fee_bps_per_side=fee,combined_spread_slippage_bps_per_side=impact,
                cost_source='Explicit hypothetical assumptions, not verified account fees or measured fills',
                scenarios=scenarios,inputs_sha256=verified['inputs_sha256'],
                runner_sha256=sha256(Path(__file__)),schedule_coverage_verified=False,
                limitations=['No signal selection or optimization; both directions shown.',
                             'Candle opens plus assumed impact are not observed executable prices.',
                             'No margin, liquidation, contract filters, exchange rounding or mark-price drawdown.',
                             'Boundary guard is a research convention, not an exchange settlement guarantee.',
                             'An accounting scenario is not a deployable futures backtest.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('first-pilot','batch-root','spot-root','funding-dir','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--fee-bps',required=True)
    p.add_argument('--impact-bps',required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        p.error('Output exists; choose a new path')
    r=run(a.first_pilot,a.batch_root,a.spot_root,a.funding_dir,a.fee_bps,a.impact_bps)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='inputs_sha256'},indent=2))


if __name__=='__main__':
    main()
