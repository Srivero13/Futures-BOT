"""Replay one validated development day as closed bars; never places orders."""
import argparse
import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal as D
from importlib.metadata import version
from pathlib import Path

from engine_v1.dataset import candles, sha256

RESERVE_MS = 1788220800000  # 2026-09-01 UTC; frozen development boundary


def day_start(value):
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError('Date must use YYYY-MM-DD')
    return int(datetime.combine(day, time(), timezone.utc).timestamp()) * 1000


def exact(value, places):
    number = D(value)
    if not number.is_finite() or number != number.quantize(D(10) ** -places):
        raise ValueError('Value exceeds supported instrument precision')
    return f'{number:.{places}f}'


def load_day(csv_path, symbol, day):
    path = Path(csv_path).resolve()
    if path.suffix != '.csv' or symbol not in ('BTCUSDT', 'ETHUSDT'):
        raise ValueError('Require canonical BTCUSDT/ETHUSDT spot CSV')
    start = day_start(day)
    end = start + 86_400_000
    if start < 0 or end > RESERVE_MS:
        raise ValueError('Requested day crosses reserved data boundary')
    sidecar = path.with_suffix('.json')
    sidecar_hash = sha256(sidecar)
    meta = json.loads(sidecar.read_text())
    digest = sha256(path)
    if (meta.get('sha256'), meta.get('venue'), meta.get('symbol'), meta.get('timeframe_ms')) != (
            digest, 'binance', symbol, 60000):
        raise ValueError('Sidecar identity/hash mismatch')
    if any(type(meta.get(k)) is not int for k in ('rows', 'first_open_ms', 'last_open_ms')):
        raise ValueError('Missing sidecar row count/range')
    if meta['last_open_ms'] >= RESERVE_MS:
        raise ValueError('Input shard crosses reserved data boundary')
    rows = []
    count = 0
    first = last = None
    for row in candles([path]):
        stamp = row['timestamp']
        if stamp < 0 or stamp >= RESERVE_MS:
            raise ValueError('Actual data crosses reserved boundary')
        if first is None:
            first = stamp
        last = stamp
        count += 1
        if start <= stamp < end:
            if stamp != start + len(rows)*60000:
                raise ValueError('Missing minute in requested day')
            rows.append(dict(timestamp=stamp,
                             **{k: exact(row[k], 8 if k == 'volume' else 2)
                                for k in ('open', 'high', 'low', 'close', 'volume')}))
    if (count, first, last) != (meta['rows'], meta['first_open_ms'], meta['last_open_ms']):
        raise ValueError('Sidecar row count/range mismatch')
    if len(rows) != 1440:
        raise ValueError('Requested day must contain exactly 1440 contiguous minutes')
    sources = {str(path): digest, str(sidecar): sidecar_hash}
    verify_sources(sources)
    return rows, sources


def verify_sources(sources):
    if any(sha256(path) != digest for path, digest in sources.items()):
        raise ValueError('Input changed during replay')


def row_bytes(stamp, values):
    return (json.dumps([stamp, *values], separators=(',', ':')) + '\n').encode()


def replay(csv_path, symbol, day):
    if version('nautilus_trader') != '1.231.0':
        raise ValueError('Expected NautilusTrader 1.231.0')
    rows, sources = load_day(csv_path, symbol, day)
    from nautilus_trader.backtest.engine import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig, LoggingConfig
    from nautilus_trader.model.currencies import BTC, ETH, USDT
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.enums import AccountType, OmsType
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Money, Price, Quantity
    from nautilus_trader.trading.strategy import Strategy

    iid = InstrumentId.from_str(symbol + '.BINANCE')
    bar_type = BarType.from_str(f'{iid}-1-MINUTE-LAST-EXTERNAL')
    instrument = CurrencyPair(
        instrument_id=iid, raw_symbol=Symbol(symbol), base_currency=BTC if symbol == 'BTCUSDT' else ETH,
        quote_currency=USDT, price_precision=2, size_precision=8,
        price_increment=Price.from_str('0.01'), size_increment=Quantity.from_str('0.00000001'),
        ts_event=0, ts_init=0)
    expected = hashlib.sha256()
    bars = []
    for row in rows:
        closed_ns = (row['timestamp'] + 60000)*1_000_000
        values = [row[k] for k in ('open', 'high', 'low', 'close', 'volume')]
        expected.update(row_bytes(closed_ns, values))
        bars.append(Bar(bar_type, *(Price.from_str(v) for v in values[:4]),
                        Quantity.from_str(values[4]), closed_ns, closed_ns))

    class Observer(Strategy):
        def __init__(self):
            super().__init__()
            self.count = 0
            self.digest = hashlib.sha256()
            self.timing_ok = True

        def on_start(self):
            self.subscribe_bars(bar_type)

        def on_bar(self, bar):
            expected_ns = (rows[0]['timestamp'] + (self.count+1)*60000)*1_000_000
            self.timing_ok &= (bar.ts_event == bar.ts_init == expected_ns == self.clock.timestamp_ns())
            self.digest.update(row_bytes(bar.ts_event,
                [str(bar.open), str(bar.high), str(bar.low), str(bar.close), str(bar.volume)]))
            self.count += 1

    observer = Observer()
    venue = Venue('BINANCE')
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggingConfig(log_level='ERROR')))
    try:
        engine.add_venue(venue=venue, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
                         starting_balances=[Money(1000, USDT)], bar_execution=False)
        engine.add_instrument(instrument)
        engine.add_strategy(observer)
        engine.add_data(bars)
        engine.run()
        checks = dict(all_minutes_received=observer.count == 1440,
                      closed_minute_timing=observer.timing_ok,
                      ohlcv_exact=observer.digest.hexdigest() == expected.hexdigest(),
                      no_orders=len(engine.cache.orders()) == 0,
                      no_positions=len(engine.cache.positions()) == 0,
                      cash_unchanged=engine.cache.account_for_venue(venue).balance_total(USDT).as_decimal() == D(1000))
    finally:
        engine.dispose()
    verify_sources(sources)
    if not all(checks.values()):
        raise ValueError(f'Historical replay failed: {checks}')
    return dict(approved=False, real_orders=False, status='historical_replay_passed',
                symbol=symbol, date=day, bars=observer.count, checks=checks,
                nautilus_version=version('nautilus_trader'), input_sha256=sources,
                replay_values_sha256=expected.hexdigest(),
                runner_sha256=sha256(__file__), dataset_reader_sha256=sha256(Path(__file__).parents[2]/'engine_v1/dataset.py'),
                limitations=['Local sidecar/hash validation; raw exchange archives are not independently reverified.',
                             'Closed spot candles only; no quotes, executable fills or performance evidence.',
                             'Instrument precision is a conversion contract, not verified historical exchange filters.',
                             'No strategy or orders; reserved September data remains excluded.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--symbol', choices=['BTCUSDT', 'ETHUSDT'], required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output exists; choose a new path.')
    result = replay(args.csv, args.symbol, args.date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
