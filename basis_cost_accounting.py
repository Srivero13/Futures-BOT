"""Explicit two-leg cost scenarios; hypothetical accounting, never orders."""
import argparse
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path


def number(value, name, positive=False):
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a decimal string')
    try:
        result=Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f'Invalid {name}') from error
    if not result.is_finite() or (result<=0 if positive else result<0):
        raise ValueError(f'Invalid {name}')
    return result


def account(scenario):
    with localcontext() as ctx:
        ctx.prec=50
        quantity=number(scenario['quantity_eth'],'quantity',True)
        direction=scenario['direction']
        if direction not in ('long_futures_short_spot','long_spot_short_futures'):
            raise ValueError('Invalid direction')
        if not isinstance(scenario.get('cost_source'),str) or not scenario['cost_source'].strip():
            raise ValueError('Explicit cost_source required')
        executions=[];reference=Decimal(0);impact=Decimal(0);fees=Decimal(0)
        for venue in ('spot','futures'):
            leg=scenario[venue]
            fee=number(leg['fee_bps_per_execution'],venue+' fee')
            slip=number(leg['slippage_bps_per_execution'],venue+' slippage')
            if fee>=10000 or slip>=10000: raise ValueError('Rates must be below 10000 bps')
            long=(venue=='spot') == (direction=='long_spot_short_futures')
            for stage in ('entry','exit'):
                bid=number(leg[stage]['bid'],venue+' bid',True)
                ask=number(leg[stage]['ask'],venue+' ask',True)
                if bid>ask: raise ValueError('Crossed bid/ask')
                buy=long == (stage=='entry')
                price=ask if buy else bid
                fill=price*(1+(slip if buy else -slip)/10000)
                cost=quantity*abs(fill-price)
                commission=quantity*fill*fee/10000
                reference+=quantity*price*(-1 if buy else 1)
                impact+=cost;fees+=commission
                executions.append(dict(venue=venue,stage=stage,side='buy' if buy else 'sell',
                    reference_price=str(price),assumed_fill=str(fill),
                    assumed_fee=str(commission),assumed_slippage_cost=str(cost)))
        notional=quantity*(number(scenario['spot']['entry']['bid'],'bid',True)+
                           number(scenario['spot']['entry']['ask'],'ask',True))/2
        subtotal=reference-impact-fees
        return dict(approved=False,cost_source=scenario['cost_source'],direction=direction,
            quantity_eth=str(quantity),reference_notional=str(notional),executions=executions,
            quote_reference_pnl=str(reference),assumed_slippage_cost=str(impact),
            assumed_fees=str(fees),subtotal_before_funding_and_financing=str(subtotal),
            omitted_costs_break_even_budget_quote=str(subtotal),
            subtotal_bps_of_entry_spot_notional=str(subtotal/notional*10000),
            limitations=['Hypothetical four-execution accounting, not observed fills or portfolio returns.',
                'Quoted spreads already enter reference prices; they are not charged again.',
                'Excludes funding, borrow, financing, margin, liquidation, filters and rounding.',
                'Short spot requires feasible inventory or borrowing; no feasibility is established.',
                'A positive subtotal is not profitability or strategy approval.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Use a new output path')
    result=account(json.loads(a.scenario.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
