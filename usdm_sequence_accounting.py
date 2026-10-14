"""Research accounting for sequential trades; callers must audit data and signals."""
from bisect import bisect_left
from decimal import Decimal, localcontext
from diagnose_usdm_roundtrip import roundtrip
from diagnose_usdm_mark_path import mark_path
from funding_cashflows import event_exposure, funding_cashflow


def decimal_string(value):
    if not isinstance(value,str):
        raise ValueError('Use decimal strings')
    d=Decimal(value)
    if not d.is_finite():
        raise ValueError('Nonfinite decimal input')
    return d


def account_sequence(trades, marks, events, fee_bps, impact_bps):
    """Single signed position at a time; reference prices are supplied, not fills."""
    for cost in (fee_bps,impact_bps):
        if not 0<=decimal_string(cost)<10000:
            raise ValueError('Invalid costs')
    mark_times=[]
    for row in marks:
        t=row['open_ms']
        if type(t) is not int or t%60000 or (mark_times and t<=mark_times[-1]):
            raise ValueError('Marks must have ordered unique minute timestamps')
        mark_times.append(t)
    event_times=[]
    for event in events:
        t=event['funding_time_ms']
        if type(t) is not int or (event_times and t<=event_times[-1]):
            raise ValueError('Funding must be ordered and unique')
        funding_cashflow('1',event['mark_price'],event['funding_rate'])
        event_times.append(t)
    previous_exit=None
    identifiers=set()
    for trade in trades:
        ident=trade['id']
        if not isinstance(ident,str) or not ident or ident in identifiers:
            raise ValueError('Trade IDs must be nonempty and unique')
        identifiers.add(ident)
        entry,exit_time=trade['entry_ms'],trade['exit_ms']
        if any(type(t) is not int or t%60000 for t in (entry,exit_time)) or entry>=exit_time:
            raise ValueError('Invalid trade interval')
        if previous_exit is not None and entry<=previous_exit:
            raise ValueError('Overlapping or simultaneous trade transitions are unsupported')
        previous_exit=exit_time
        if decimal_string(trade['quantity'])==0 or min(decimal_string(trade['entry_reference']),decimal_string(trade['exit_reference']))<=0:
            raise ValueError('Invalid quantity or reference price')
    with localcontext() as ctx:
        ctx.prec=50
        realized=peak=drawdown=Decimal(0)
        envelope_peak=envelope_minimum=envelope_drawdown=Decimal(0)
        fees=impact=funding=reference=Decimal(0)
        output=[];path=[];assigned=set()
        for trade in trades:
            entry,exit_time=trade['entry_ms'],trade['exit_ms']
            scenario=roundtrip(trade['quantity'],trade['entry_reference'],trade['exit_reference'],
                               entry,exit_time,events,fee_bps,impact_bps)
            left,right=bisect_left(mark_times,entry),bisect_left(mark_times,exit_time)
            valued=mark_path(scenario,marks[left:right],events,fee_bps)
            # Carry earlier peaks into later trades without summing drawdowns.
            lower=realized+Decimal(valued['ohlc_pnl_lower_bound_quote'])
            upper=realized+Decimal(valued['ohlc_pnl_upper_bound_quote'])
            envelope_drawdown=max(envelope_drawdown,
                envelope_peak-lower,Decimal(valued['ohlc_drawdown_upper_bound_quote']))
            envelope_minimum=min(envelope_minimum,lower)
            envelope_peak=max(envelope_peak,upper)
            held={t for t in event_times if event_exposure(entry,exit_time,t)=='held'}
            if held & assigned:
                raise ValueError('Funding event assigned to multiple trades')
            assigned.update(held)
            for point in valued['path']:
                pnl=realized+Decimal(point['pnl'])
                peak=max(peak,pnl);drawdown=max(drawdown,peak-pnl)
                path.append(dict(trade_id=trade['id'],timestamp_ms=point['timestamp_ms'],
                                 kind=point['kind'],cumulative_pnl=str(pnl)))
            realized+=Decimal(scenario['scenario_net_pnl'])
            fees+=Decimal(scenario['assumed_fees'])
            impact+=Decimal(scenario['assumed_price_impact_cost'])
            funding+=Decimal(scenario['unambiguous_funding_cashflow'])
            reference+=Decimal(scenario['reference_price_pnl'])
            output.append(dict(id=trade['id'],accounting=scenario,
                               cumulative_realized_pnl=str(realized)))
        if realized!=reference-impact-fees+funding:
            raise ValueError('Sequence accounting does not reconcile')
        return dict(approved=False,closed_trades=len(trades),net_pnl=str(realized),
                    reference_price_pnl=str(reference),assumed_fees=str(fees),
                    assumed_price_impact_cost=str(impact),funding_cashflow=str(funding),
                    assigned_funding_events=len(assigned),unassigned_funding_events=len(events)-len(assigned),
                    max_sampled_drawdown_quote=str(drawdown),
                    ohlc_drawdown_upper_bound_quote=str(envelope_drawdown),
                    ohlc_pnl_lower_bound_quote=str(envelope_minimum),
                    bound_scope='Supplied mark extrema and funding; unknown intraminute ordering; not liquidation risk',
                    accounting_reconciled=True,
                    trades=output,path=path,
                    limitations=['Accounting primitive: supplied reference prices and timestamps are not independently verified fills or causal signals.',
                                 'No capital, sizing, exchange filters, margin or liquidation model.',
                                 'Sampled drawdown and a conservative OHLC bound are separate; neither is a sum of trade drawdowns or a liquidation calculation.',
                                 'Funding uses supplied events only; no source completeness guarantee.'])
