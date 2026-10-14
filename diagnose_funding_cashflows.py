"""Unit-exposure funding arithmetic over audited events, not portfolio P&L."""
import argparse
from datetime import date
from decimal import Decimal, localcontext
import json
from pathlib import Path

from audit_usdm_funding import audit
from engine_v1.dataset import sha256
from funding_cashflows import funding_cashflow


def diagnose(root, symbol, start, end, reserve):
    verification = audit(root, symbol, start, end, reserve)
    path = Path(root)/'funding.json'
    rows = json.loads(path.read_text())
    events = []
    with localcontext() as context:
        context.prec = 50
        total = Decimal(0)
        for row in rows:
            if row['mark_price'] is None:
                raise ValueError('Missing settlement mark; no cash-flow total can be reported')
            long_flow = funding_cashflow('1', row['mark_price'], row['funding_rate'])
            short_flow = funding_cashflow('-1', row['mark_price'], row['funding_rate'])
            if long_flow + short_flow != 0:
                raise ValueError('Long/short accounting failed to balance')
            total += long_flow
            events.append(dict(funding_time_ms=row['funding_time_ms'],
                               mark_price=row['mark_price'], funding_rate=row['funding_rate'],
                               long_one_base_unit_cashflow=str(long_flow),
                               short_one_base_unit_cashflow=str(short_flow)))
        short_total = str(-total)
    if any(sha256(p)!=h for p,h in verification['inputs_sha256'].items()):
        raise ValueError('Audited inputs changed during calculation')
    return dict(approved=False, symbol=symbol, start=str(start), end_exclusive=str(end),
                scenario='Separate hypothetical +1 and -1 base-unit exposures at every recorded event',
                events=len(events), long_funding_cashflow=str(total), short_funding_cashflow=short_total,
                positive_cashflow_means='receipt', event_cashflows=events,
                schedule_coverage_verified=False, inputs_sha256=verification['inputs_sha256'],
                runner_sha256=sha256(Path(__file__)),
                arithmetic_sha256=sha256(Path(__file__).with_name('funding_cashflows.py')),
                limitations=['Exposure at every recorded event is assumed, not reconstructed from trades.',
                             'No entry/exit orders, leverage, exchange rounding or liquidation modeling.',
                             'Funding component only: excludes price P&L, fees and slippage.',
                             'Historical schedule remains unverified; missing events are not zero payments.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--funding-dir',type=Path,required=True)
    p.add_argument('--symbol',default='ETHUSDT')
    p.add_argument('--start',type=date.fromisoformat,required=True)
    p.add_argument('--end',type=date.fromisoformat,required=True)
    p.add_argument('--reserve-from',type=date.fromisoformat,default=date(2026,9,1))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        p.error('Output exists; choose a new report path')
    report=diagnose(a.funding_dir,a.symbol,a.start,a.end,a.reserve_from)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        f.write(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('event_cashflows','inputs_sha256')},indent=2))


if __name__=='__main__':
    main()
