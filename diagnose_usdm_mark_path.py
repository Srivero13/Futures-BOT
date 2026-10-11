"""Fixed-exposure minute-close P&L path; no capital, margin or liquidation model."""
import argparse
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json
from pathlib import Path
from batch_usdm_marks import audit_marks
from diagnose_usdm_roundtrip import run as verify_roundtrip
from engine_v1.dataset import sha256
from funding_cashflows import event_exposure, funding_cashflow


def mark_path(scenario, marks, events, fee_bps):
    """Include entry fees immediately, held funding at event time, exit costs at exit."""
    if not scenario['accounting_resolved_for_supplied_events']:
        raise ValueError('Ambiguous funding boundaries prevent path calculation')
    entry, exit_time = scenario['entry_ms'], scenario['exit_ms']
    if entry % 60000 or exit_time % 60000:
        raise ValueError('Minute-aligned entry and exit required')
    with localcontext() as ctx:
        ctx.prec = 50
        q = Decimal(scenario['quantity'])
        fill = Decimal(scenario['entry_fill_assumption'])
        fee = Decimal(fee_bps)
        if not fee.is_finite() or not 0 <= fee < 10000:
            raise ValueError('Invalid fee')
        cash = -abs(q) * fill * fee / 10000
        held = []
        last = None
        for event in events:
            t = event['funding_time_ms']
            if type(t) is not int or (last is not None and t <= last):
                raise ValueError('Funding must be ordered and unique')
            last = t
            exposure = event_exposure(entry, exit_time, t)
            if exposure == 'ambiguous':
                raise ValueError('Ambiguous funding boundary')
            if exposure == 'held':
                held.append((t, funding_cashflow(str(q), event['mark_price'], event['funding_rate'])))
        rows = []
        peak = Decimal(0)
        drawdown = Decimal(0)
        def append(t, kind, pnl):
            nonlocal peak, drawdown
            peak = max(peak, pnl)
            drawdown = max(drawdown, peak - pnl)
            rows.append(dict(timestamp_ms=t, kind=kind, pnl=str(pnl)))
        # Entry impact becomes visible at the first mark; this point charges entry fees only.
        append(entry, 'entry_fee_only', cash)
        cursor = entry
        funding = Decimal(0)
        index = 0
        for row in marks:
            t = row['open_ms']
            if not entry <= t < exit_time:
                continue
            if type(t) is not int or t != cursor:
                raise ValueError('Missing or unordered held-period mark minute')
            close = Decimal(row['close'])
            if not close.is_finite() or close <= 0:
                raise ValueError('Invalid close mark')
            receipt = t + 59999
            while index < len(held) and held[index][0] <= receipt:
                funding += held[index][1]
                index += 1
            append(receipt, 'mark_close', cash + funding + q * (close - fill))
            cursor += 60000
        if cursor != exit_time or index != len(held):
            raise ValueError('Incomplete mark or funding coverage')
        net = cash + funding + q * (Decimal(scenario['exit_fill_assumption']) - fill)
        net -= abs(q) * Decimal(scenario['exit_fill_assumption']) * fee / 10000
        if net != Decimal(scenario['scenario_net_pnl']):
            raise ValueError('Terminal P&L does not reconcile with round trip')
        append(exit_time, 'realized_exit', net)
        return dict(mark_minutes=(exit_time-entry)//60000,
                    max_sampled_drawdown_quote=str(drawdown),
                    minimum_sampled_pnl_quote=str(min(Decimal(r['pnl']) for r in rows)),
                    terminal_net_pnl=str(net), terminal_reconciled=True, path=rows)


def run(first, batch, spot, funding, marks_first, marks_batch, fee, impact):
    accounting = verify_roundtrip(first, batch, spot, funding, fee, impact)
    hashes = dict(accounting['inputs_sha256'])
    marks = []
    for i in range(7):
        day = date(2026, 8, 1) + timedelta(days=i)
        folder = Path(marks_first) if i == 0 else Path(marks_batch)/str(day)
        print(f'[mark-path] auditing {day}', flush=True)
        audit = audit_marks(folder, day)
        hashes.update(audit['inputs_sha256'])
        marks.extend(json.loads((folder/'marks.json').read_text()))
    events = json.loads((Path(funding)/'funding.json').read_text())
    scenarios = {name: mark_path(s, marks, events, fee) for name, s in accounting['scenarios'].items()}
    if any(sha256(p) != h for p, h in hashes.items()):
        raise ValueError('Inputs changed during path calculation')
    return dict(approved=False, symbol='ETHUSDT', scenarios=scenarios,
                fee_bps_per_side=fee, combined_spread_slippage_bps_per_side=impact,
                cost_source=accounting['cost_source'], inputs_sha256=hashes,
                runner_sha256=sha256(Path(__file__)), schedule_coverage_verified=False,
                limitations=['Fixed hypothetical exposures, not a strategy or executable backtest.',
                             'Drawdown uses minute closes plus entry-fee and realized-exit points; intraminute losses are not reconstructed.',
                             'No initial capital, percentage return, margin, liquidation or contract-filter model.',
                             'Funding completeness remains unverified; accounting uses supplied events only.'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('first-pilot', 'batch-root', 'spot-root', 'funding-dir', 'marks-first', 'marks-batch', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--fee-bps', required=True)
    p.add_argument('--impact-bps', required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        p.error('Output exists; choose a new path')
    result = run(a.first_pilot, a.batch_root, a.spot_root, a.funding_dir,
                 a.marks_first, a.marks_batch, a.fee_bps, a.impact_bps)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as f:
        f.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps({name: {k:v for k,v in s.items() if k!='path'}
                      for name,s in result['scenarios'].items()}, indent=2))
    print(f'Completed: {a.output}; accounting only, unapproved.')


if __name__ == '__main__':
    main()
