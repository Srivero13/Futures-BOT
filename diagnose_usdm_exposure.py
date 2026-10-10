"""Fixed week reference-price and funding attribution; no strategy or fills."""
import argparse
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json
from pathlib import Path

from audit_usdm_pilot import audit
from diagnose_funding_cashflows import diagnose
from engine_v1.dataset import candles, sha256


def components(opening, closing, long_funding):
    with localcontext() as context:
        context.prec=50
        o,c,f=map(Decimal,(opening,closing,long_funding))
        if not all(v.is_finite() for v in (o,c,f)) or min(o,c)<=0:
            raise ValueError('Invalid reference prices or funding')
        movement=c-o
        return {'long_one_eth': {'reference_price_change':str(movement),'funding':str(f),
                                 'combined_before_trading_costs':str(movement+f)},
                'short_one_eth': {'reference_price_change':str(-movement),'funding':str(-f),
                                  'combined_before_trading_costs':str(-movement-f)}}


def run(first_pilot, batch_root, spot_root, funding_root):
    # Fixed week avoids selecting favorable start/end dates after seeing outcomes.
    start,end,reserve=date(2026,8,1),date(2026,8,8),date(2026,9,1)
    sources={}
    opening=closing=None
    total=0
    for i in range(7):
        day=start+timedelta(days=i)
        folder=Path(first_pilot) if i==0 else Path(batch_root)/str(day)
        spot=Path(spot_root)/'binance-ETHUSDT-2026-08.csv'
        print(f'[exposure] auditing day {i+1}/7: {day}',flush=True)
        report=audit(folder,spot,'ETHUSDT',day,reserve)
        for path,digest in report['inputs_sha256'].items():
            if path in sources and sources[path]!=digest:
                raise ValueError('Shared input changed between daily audits')
            sources[path]=digest
        rows=list(candles([folder/f'binance-usdm-ETHUSDT-{day}.csv']))
        if i==0:
            opening=rows[0]['open']
        closing=rows[-1]['close']
        total+=len(rows)
    funding=diagnose(funding_root,'ETHUSDT',start,end,reserve)
    for path,digest in funding['inputs_sha256'].items():
        if path in sources and sources[path]!=digest:
            raise ValueError('Shared funding input changed')
        sources[path]=digest
    if any(sha256(p)!=h for p,h in sources.items()):
        raise ValueError('Inputs changed before attribution completed')
    return dict(approved=False,symbol='ETHUSDT',start=str(start),end_exclusive=str(end),
                minutes=total,funding_events=funding['events'],
                opening_trade_price=opening,closing_trade_price=closing,
                scenarios=components(opening,closing,funding['long_funding_cashflow']),
                inputs_sha256=sources,runner_sha256=sha256(Path(__file__)),
                schedule_coverage_verified=False,
                limitations=['Assumes separate constant +1/-1 ETH exposures already held before the first funding event.',
                             'First open and last close are valuation references, not entry/exit fills or mark-price equity.',
                             'Excludes trading fees, spread, slippage, margin, liquidation and exchange rounding.',
                             'No side selection, signals, strategy backtest, return on capital or profitability evidence.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--first-pilot',type=Path,required=True)
    p.add_argument('--batch-root',type=Path,required=True)
    p.add_argument('--spot-root',type=Path,required=True)
    p.add_argument('--funding-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        p.error('Output exists; choose a new report path')
    r=run(a.first_pilot,a.batch_root,a.spot_root,a.funding_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='inputs_sha256'},indent=2))


if __name__=='__main__':
    main()
