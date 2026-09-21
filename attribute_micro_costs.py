"""Attribute saved closed-trade costs without changing signals or replaying data."""
import argparse
from decimal import Decimal,localcontext
import json
from pathlib import Path
import sys
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json

D=Decimal


def dec(value):
    x=D(str(value))
    if not x.is_finite():raise ValueError('Non-finite monetary value')
    return x


def analyze(report):
    with localcontext() as ctx:
        ctx.prec=50
        p=report['protocol'];summary=report['summary'];trades=report['closed_trades']
        if len(trades)!=summary['closed_trades']:raise ValueError('Trade count mismatch')
        slip=dec(p['slippage_bps_per_side'])/10000;fee=dec(p['fee_bps_per_side'])/10000
        if not 0<=slip<1 or not 0<=fee<1:raise ValueError('Invalid assumptions')
        totals={k:D(0) for k in ('midpoint_pnl','observed_spread_cost','assumed_slippage_cost','fees','net_pnl','reference_turnover','reference_gross_pnl')}
        for t in trades:
            q,buy,sell=map(dec,(t['quantity'],t['entry_price'],t['exit_price']))
            if min(q,buy,sell)<=0:raise ValueError('Invalid trade quantity/prices')
            ask=buy/(1+slip);bid=sell/(1-slip)
            midpoint=dec(t['midpoint_pnl']);gross=q*(sell-buy);reference=q*(bid-ask)
            recorded_fee=dec(t['fees']);net=dec(t['net_pnl'])
            checks=[gross-recorded_fee-net,recorded_fee-q*(buy+sell)*fee,
                midpoint-gross-dec(t['spread_slippage_cost']),q*buy-dec(t['entry_notional'])]
            if any(abs(v)>D('1e-18') for v in checks):raise ValueError('Saved trade identity mismatch')
            totals['midpoint_pnl']+=midpoint;totals['observed_spread_cost']+=midpoint-reference
            totals['assumed_slippage_cost']+=reference-gross;totals['fees']+=recorded_fee
            totals['net_pnl']+=net;totals['reference_turnover']+=q*(ask+bid);totals['reference_gross_pnl']+=reference
        for key in ('midpoint_pnl','fees','net_pnl'):
            if abs(totals[key]-dec(summary['closed_trade_totals'][key]))>D('1e-18'):raise ValueError('Report totals mismatch')
        if abs(totals['observed_spread_cost']+totals['assumed_slippage_cost']-dec(summary['closed_trade_totals']['spread_slippage_cost']))>D('1e-18'):
            raise ValueError('Combined cost mismatch')
        turnover=totals['reference_turnover'];gross=totals['reference_gross_pnl']
        return {'closed_trades':len(trades),'unresolved_positions':summary['unresolved_positions'],
            'totals':{k:str(v) for k,v in totals.items()},
            'zero_slippage_zero_fee_net':str(gross),
            'zero_slippage_break_even_fee_bps_per_side':str(gross/turnover*10000) if turnover else None,
            'nonnegative_fee_can_break_even_without_slippage':bool(turnover and gross>=0),
            'zero_slippage_fee_scenarios':[{'fee_bps_per_side':f,'closed_trade_net':str(gross-turnover*D(f)/10000)} for f in (0,1,5,10)],
            'complete_execution_result':False}


def run(source,output):
    source=Path(source);output=Path(output)
    if output.exists():raise ValueError('Output exists; choose a new filename')
    digest=sha256(source);report=json.loads(source.read_text());summary=analyze(report)
    if sha256(source)!=digest:raise ValueError('Source report changed')
    atomic_json(output,{'approved':False,'summary':summary,'source_sha256':digest,'source':str(source.resolve()),
        'runner_sha256':sha256(Path(__file__)),
        'limitations':['Uses only previously completed simulated trades; unresolved positions and selection effects remain.',
        'Same quantities and entry/exit times are held fixed, including in zero-slippage scenarios; no resimulation of exposure or fills.',
        'Reference ask/bid are recovered from saved fill prices and the declared multiplicative slippage assumption.',
        'Break-even fees are algebraic bounds for this subset, not available broker rates or a profitable strategy.',
        'Zero slippage and zero fees are idealized sensitivity cases; maker fills or rebates are not modeled.',
        'No parameter selection, new holdout, live orders, or model approval.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(run(a.report,a.output),indent=2))
    except (ValueError,OSError,KeyError,TypeError,ArithmeticError) as error:
        print(f'Cost attribution stopped: {error}',file=sys.stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
