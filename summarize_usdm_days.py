"""Attribute a saved continuous fixed-exposure P&L path to UTC days."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path
from engine_v1.dataset import sha256


def number(value):
    if not isinstance(value, str):
        raise ValueError('Decimal strings required')
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError('Nonfinite P&L')
    return result


def summarize(scenario):
    with localcontext() as ctx:
        ctx.prec = 50
        rows = scenario['path']
        if not isinstance(rows, list) or len(rows) < 3 or scenario.get('terminal_reconciled') is not True:
            raise ValueError('Incomplete scenario')
        start, end = rows[0]['timestamp_ms'], rows[-1]['timestamp_ms']
        if any(type(t) is not int for t in (start, end)) or start % 60000 or end % 60000 or end <= start:
            raise ValueError('Invalid exposure interval')
        minutes = (end-start)//60000
        if scenario['mark_minutes'] != minutes or len(rows) != minutes+2:
            raise ValueError('Path minute count mismatch')
        previous = peak = drawdown = Decimal(0)
        minimum = None
        days = {}
        for index, row in enumerate(rows):
            expected_t = start if index == 0 else end if index == len(rows)-1 else start+(index-1)*60000+59999
            expected_kind = 'entry_fee_only' if index == 0 else 'realized_exit' if index == len(rows)-1 else 'mark_close'
            if type(row['timestamp_ms']) is not int or row['timestamp_ms'] != expected_t or row['kind'] != expected_kind:
                raise ValueError('Invalid path order, coverage or point type')
            pnl = number(row['pnl'])
            day = datetime.fromtimestamp(expected_t//1000, timezone.utc).date().isoformat()
            if day not in days:
                days[day] = dict(date=day, opening_cumulative_pnl=previous, net_change=Decimal(0), points=0)
            d = days[day]
            d['net_change'] += pnl-previous
            d['closing_cumulative_pnl'] = pnl
            d['points'] += 1
            previous = pnl
            peak = max(peak, pnl)
            drawdown = max(drawdown, peak-pnl)
            minimum = pnl if minimum is None else min(minimum, pnl)
        total = sum((d['net_change'] for d in days.values()), Decimal(0))
        if total != number(scenario['terminal_net_pnl']) or drawdown != number(scenario['max_sampled_drawdown_quote']) or minimum != number(scenario['minimum_sampled_pnl_quote']):
            raise ValueError('Saved summary disagrees with path')
        daily = list(days.values())
        best = max(daily, key=lambda d:d['net_change'])
        worst = min(daily, key=lambda d:d['net_change'])
        return dict(days=len(daily), positive_days=sum(d['net_change']>0 for d in daily),
                    terminal_net_pnl=str(total), daily_sum_reconciled=True,
                    best_day=best['date'], best_day_change=str(best['net_change']),
                    worst_day=worst['date'], worst_day_change=str(worst['net_change']),
                    net_excluding_best_day_change=str(total-best['net_change']),
                    daily=[{k:str(v) if isinstance(v,Decimal) else v for k,v in d.items()} for d in daily])


def run(report):
    report = Path(report)
    digest = sha256(report)
    data = json.loads(report.read_text())
    if data.get('approved') is not False or data.get('symbol') != 'ETHUSDT' or set(data['scenarios']) != {'long_one_eth','short_one_eth'}:
        raise ValueError('Unexpected research report identity')
    hashes = data['inputs_sha256']
    if not isinstance(hashes,dict) or not hashes or any(sha256(p)!=h for p,h in hashes.items()):
        raise ValueError('Saved source inputs missing or changed')
    result = dict(approved=False, symbol='ETHUSDT', timezone='UTC',
                  scenarios={k:summarize(v) for k,v in data['scenarios'].items()},
                  source_report_sha256=digest, runner_sha256=sha256(Path(__file__)),
                  limitations=['Daily changes attribute one continuous hypothetical position; no daily resets or independent trades.',
                               'Excluding the best day is arithmetic sensitivity, not an executable alternative strategy.',
                               'Includes the source scenario cost assumptions and supplied funding; no profitability approval.',
                               'Checks saved paths and source hashes; does not independently rebuild market accounting.'])
    if sha256(report)!=digest or any(sha256(p)!=h for p,h in hashes.items()):
        raise ValueError('Inputs changed during attribution')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        p.error('Output exists; choose a new path')
    result=run(a.report)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
