"""Replay frozen WBC01 trades against minute reference prices; research only."""
import argparse
from decimal import Decimal as D, localcontext
import json
from pathlib import Path

from engine_v1.dataset import candles, sha256
from engine_v1.research_artifacts import read_json
from research_weekly_btc import START, END, MINUTE, PROTOCOL, build_schedule, simulate


def replay(rows, scenarios, start=START, end=END):
    with localcontext() as ctx:
        ctx.prec = 50
        states = {}
        for name, scenario in scenarios.items():
            events = {}
            previous_exit = start - 1
            for trade in scenario['trades']:
                entry, exit_time = trade['entry_ms'], trade['exit_ms']
                if not start <= entry < exit_time < end or entry <= previous_exit or entry % MINUTE or exit_time % MINUTE:
                    raise ValueError('Invalid or overlapping trade times')
                previous_exit = exit_time
                events[entry] = ('entry', trade)
                events[exit_time] = ('exit', trade)
            states[name] = dict(cash=D(1000), quantity=D(0), peak=D(1000), bound_peak=D(1000),
                minimum=D(1000), lower=D(1000), dd=D(0), bound_dd=D(0), events=events,
                consumed=0, held_minutes=0)

        def point(s, value):
            s['peak'] = max(s['peak'], value)
            s['dd'] = max(s['dd'], (s['peak']-value)/s['peak']*100)
            s['minimum'] = min(s['minimum'], value)
            envelope(s, value, value)

        def envelope(s, low, high):
            s['bound_peak'] = max(s['bound_peak'], high)
            s['bound_dd'] = max(s['bound_dd'], (s['bound_peak']-low)/s['bound_peak']*100)
            s['lower'] = min(s['lower'], low)

        expected = start
        for row in rows:
            t = row['timestamp']
            if t < start:
                continue
            if t >= end:
                break
            if t != expected:
                raise ValueError('Missing or unordered development minute')
            expected += MINUTE
            prices = {k:D(row[k]) for k in ('open','high','low','close')}
            if not all(v.is_finite() and v > 0 for v in prices.values()) or not prices['low'] <= min(prices['open'], prices['close']) <= max(prices['open'], prices['close']) <= prices['high']:
                raise ValueError('Invalid OHLC')
            for s in states.values():
                point(s, s['cash'] + s['quantity']*prices['open'])
                if t in s['events']:
                    kind, trade = s['events'][t]
                    if D(trade[kind+'_price']) != prices['open']:
                        raise ValueError('Saved trade reference differs from candle open')
                    if kind == 'entry':
                        s['quantity'] = D(trade['quantity'])
                        s['cash'] -= D(trade['entry_outlay'])
                    else:
                        s['cash'] += s['quantity']*D(trade['exit_fill'])-D(trade['exit_fee'])
                        s['quantity'] = D(0)
                    s['consumed'] += 1
                    point(s, s['cash']+s['quantity']*prices['open'])
                # The exit takes place at the open, before this minute's extrema.
                envelope(s, s['cash']+s['quantity']*prices['low'], s['cash']+s['quantity']*prices['high'])
                point(s, s['cash']+s['quantity']*prices['close'])
                s['held_minutes'] += bool(s['quantity'])
            if (expected-start)//MINUTE % 200000 == 0:
                print(f'[weekly-risk] minutes={(expected-start)//MINUTE:,}', flush=True)
        if expected != end:
            raise ValueError('Incomplete development interval')
        results = {}
        for name,s in states.items():
            source = scenarios[name]
            if s['quantity'] or s['consumed'] != len(s['events']) or abs(s['cash']-D(source['ending_cash'])) > D('1e-40') or abs(s['cash']-1000-D(source['net_pnl'])) > D('1e-40'):
                raise ValueError('Terminal reconciliation failed')
            results[name] = dict(minutes=(end-start)//MINUTE, held_minutes=s['held_minutes'],
                max_minute_sampled_drawdown_pct=s['dd'], ohlc_drawdown_upper_bound_pct=s['bound_dd'],
                minimum_sampled_equity=s['minimum'], ohlc_equity_lower_bound=s['lower'],
                terminal_net_pnl=s['cash']-1000, terminal_reconciled=True)
        return results


def run(path):
    saved, report_hash = read_json(path)
    protocol, protocol_hash = read_json(PROTOCOL)
    if protocol_hash != 'cadb03783056b7f4a17dd043210be015641d5e34f0dcb0f7dc6991d94631c74f':
        raise ValueError('Frozen protocol changed')
    if saved.get('approved') is not False or saved.get('experiment') != 'WBC01' or saved.get('protocol') != protocol or saved.get('protocol_sha256') != protocol_hash:
        raise ValueError('Wrong experiment or changed protocol')
    sources = saved['sources']
    if not sources or any(sha256(p) != h for p,h in sources.items()):
        raise ValueError('Source hash mismatch')
    paths = sorted(Path(p) for p in sources if Path(p).suffix == '.csv')
    if not paths:
        raise ValueError('No source candles')
    for p in paths:
        meta, h = read_json(p.with_suffix('.json'))
        if sources.get(str(p.with_suffix('.json'))) != h or meta.get('sha256') != sources[str(p)] or (meta.get('venue'),meta.get('symbol'),meta.get('timeframe_ms')) != ('binance','BTCUSDT',60000) or type(meta.get('last_open_ms')) is not int or meta['last_open_ms'] >= END:
            raise ValueError('Invalid or reserved source shard')
    decisions, events = build_schedule(candles(paths))
    if decisions != saved['decisions']:
        raise ValueError('Saved decisions differ from reconstructed rule')
    scenarios = {}
    for name, impact, hold in [('base','2',False),('stress','3',False),('buy_and_hold','2',True)]:
        rebuilt = simulate(events, impact, hold=hold)
        if json.loads(json.dumps(rebuilt, default=str)) != saved[name]:
            raise ValueError(f'Saved {name} accounting differs from reconstruction')
        scenarios[name] = rebuilt
    results = replay(candles(paths), scenarios)
    if sha256(path) != report_hash or sha256(PROTOCOL) != protocol_hash or any(sha256(p) != h for p,h in sources.items()):
        raise ValueError('Inputs changed during replay')
    return dict(approved=False, experiment='WBC01', source_report_sha256=report_hash,
        sources=sources, protocol_sha256=protocol_hash,
        code_sha256={p:sha256(Path(__file__).parent/p) for p in ('diagnose_weekly_btc_risk.py','research_weekly_btc.py','engine_v1/dataset.py')},
        scenarios=results, limitations=[
            'Previously used development data; no promotion or parameter selection.',
            'Minute opens/closes are sampled reference equity, not executable liquidation value.',
            'OHLC bound allows high before low within a minute; their true order is unknown.',
            'Entry/exit occur at saved assumed fills at candle opens; exit-minute later extrema are excluded.',
            'Bound covers supplied candles and assumed costs only, not unobserved prices or execution risk.',
            'Lower drawdown with less market exposure does not establish risk-adjusted outperformance.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Use a new output path')
    result = run(args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result, f, default=str, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps(result['scenarios'], default=str, indent=2))


if __name__ == '__main__':
    main()
