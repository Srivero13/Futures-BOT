"""Saved-trade concentration and fixed-quantity slippage sensitivity; no refitting."""
import argparse
from decimal import Decimal, localcontext
import json
from pathlib import Path

from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json


def dec(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Non-finite number')
    return result


def analyze(report):
    with localcontext() as context:
        context.prec = 50
        return _analyze(report)


def _analyze(report):
    protocol = report['protocol']
    if protocol.get('hypothesis') != '20-minute upward trend continuation over a 60-minute holding period':
        raise ValueError('Expected hourly trend development report')
    if not report['folds']:
        raise ValueError('No folds')
    costs = protocol['costs']
    fee = dec(costs['fee_bps']) / 10000
    impact = (dec(costs['spread_bps'])/2 + dec(costs['slippage_bps']))/10000
    if not 0 <= fee < 1 or not 0 <= impact < 1:
        raise ValueError('Invalid costs')
    scenarios = {extra: [] for extra in ('0', '0.5', '1', '2')}
    all_trades = []
    seen_months = set()
    previous_exit = None
    for fold in report['folds']:
        month = fold['test_start']
        if month in seen_months or fold['assumptions'] != costs:
            raise ValueError('Duplicate month or inconsistent costs')
        seen_months.add(month)
        trades = fold['trades']
        if len(trades) != fold['summary']['closed_trades']:
            raise ValueError('Trade count mismatch')
        monthly = {extra: Decimal(0) for extra in scenarios}
        for trade in trades:
            decision, entry, exit_ = (trade[k] for k in ('decision_ms', 'entry_ms', 'exit_ms'))
            if any(type(t) is not int for t in (decision, entry, exit_)):
                raise ValueError('Invalid timestamps')
            if entry-decision != 60000 or exit_-entry != 3600000 or (previous_exit is not None and entry < previous_exit):
                raise ValueError('Invalid trade timing or overlap')
            previous_exit = exit_
            q, buy, sell = (dec(trade[k]) for k in ('quantity', 'entry_price', 'exit_price'))
            if min(q, buy, sell) <= 0:
                raise ValueError('Invalid fill')
            original = q*(sell*(1-fee)-buy*(1+fee))
            if abs(original-dec(trade['net_pnl'])) > Decimal('1e-25'):
                raise ValueError('Trade accounting mismatch')
            if abs(q*(buy+sell)*fee-dec(trade['fees'])) > Decimal('1e-25'):
                raise ValueError('Fee accounting mismatch')
            all_trades.append(original)
            for extra in scenarios:
                new_impact = impact+dec(extra)/10000
                if new_impact >= 1:
                    raise ValueError('Invalid stressed impact')
                new_buy = buy/(1+impact)*(1+new_impact)
                new_sell = sell/(1-impact)*(1-new_impact)
                monthly[extra] += q*(new_sell*(1-fee)-new_buy*(1+fee))
        if abs(monthly['0']-dec(fold['summary']['net_pnl'])) > Decimal('1e-25'):
            raise ValueError('Monthly accounting mismatch')
        for extra in scenarios:
            scenarios[extra].append({'month': month[:7], 'net_pnl': str(monthly[extra])})
    total = sum(all_trades, Decimal(0))
    if len(all_trades) != report['summary']['closed_trades'] or abs(total-dec(report['summary']['sum_independent_month_net_pnl'])) > Decimal('1e-25'):
        raise ValueError('Aggregate accounting mismatch')
    best = max(all_trades) if all_trades else None
    worst = min(all_trades) if all_trades else None
    return {
        'closed_trades': len(all_trades), 'net_pnl': str(total),
        'best_trade_net_pnl': str(best) if best is not None else None,
        'worst_trade_net_pnl': str(worst) if worst is not None else None,
        'net_pnl_excluding_best_trade': str(total-best) if best is not None else None,
        'positive_without_best_trade': total-best > 0 if best is not None else None,
        'slippage_scenarios': [
            {'extra_slippage_bps_per_side': extra,
             'sum_independent_month_net_pnl': str(sum((dec(m['net_pnl']) for m in months), Decimal(0))),
             'positive_months': sum(dec(m['net_pnl']) > 0 for m in months),
             'monthly': months} for extra, months in scenarios.items()],
    }


def run(path, output):
    if output.exists():
        raise ValueError('Output exists; choose a new filename')
    digest = sha256(path)
    report = json.loads(path.read_text())
    if sha256(path) != digest:
        raise ValueError('Input changed')
    summary = analyze(report)
    atomic_json(output, {'approved': False, 'summary': summary,
        'source': {'path': str(path.resolve()), 'sha256': digest},
        'runner_sha256': sha256(Path(__file__)),
        'limitations': [
            'Saved simulated fills only; raw market data and strategy are not replayed.',
            'Quantities, entry/exit times and selected trades stay fixed; fees recomputed on stressed fills.',
            'A full rerun could change sizing, cash constraints and the cost-scaled entry filter.',
            'Removing the best trade is a concentration diagnostic, not a tradable strategy.',
            'Monthly capital resets; summed P&L is not compounded. No significance or approval claim.',
        ]})
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    try:
        print(json.dumps(run(a.report, a.output), indent=2))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        p.exit(2, f'Robustness diagnostic stopped: {exc}\n')


if __name__ == '__main__':
    main()
