"""Read-only bridge from Futures-BOT canonical Binance 1m shards to NautilusTrader v2.

No credentials, live adapters, portfolio databases, or order submission.
All bars become visible at their CLOSE, never their source open timestamp.
"""
import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import time

VERSION = '2.0.0rc7'
SYMBOLS = {'BTCUSDT': 'BTC', 'ETHUSDT': 'ETH'}
FIELDS = {'timestamp', 'open', 'high', 'low', 'close', 'volume'}


@dataclass(frozen=True)
class Candle:
    open_second: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @property
    def close_ns(self):
        return (self.open_second + 60) * 1_000_000_000


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            checksum.update(chunk)
    return checksum.hexdigest()


def validated_shards(paths, symbol):
    """Validate all source identities/hashes before parsing data."""
    if symbol not in SYMBOLS:
        raise ValueError('Only Binance spot BTCUSDT and ETHUSDT are supported')
    if not paths:
        raise ValueError('At least one CSV shard is required')
    output = []
    for raw in paths:
        path = Path(raw)
        if not path.is_file() or path.suffix != '.csv':
            raise ValueError('Expected a canonical .csv shard: ' + str(path))
        sidecar = path.with_suffix('.json')
        if not sidecar.is_file():
            raise ValueError('Missing shard provenance sidecar: ' + str(sidecar))
        meta = json.loads(sidecar.read_text())
        actual_hash = digest(path)
        expected = {'venue': 'binance', 'symbol': symbol, 'timeframe_ms': 60000,
                    'sha256': actual_hash, 'bytes': path.stat().st_size}
        if any(meta.get(k) != v for k, v in expected.items()):
            raise ValueError('Source identity/checksum mismatch: ' + str(path))
        if type(meta.get('rows')) is not int or meta['rows'] < 1:
            raise ValueError('Invalid sidecar row count: ' + str(path))
        output.append((path, meta))
    return output


def decimal_value(raw, name):
    try:
        value = Decimal(raw)
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid numeric ' + name) from None
    if not value.is_finite() or (value <= 0 if name != 'volume' else value < 0):
        raise ValueError('Invalid ' + name + ': must be finite and nonnegative/positive')
    if -value.as_tuple().exponent > 8:
        raise ValueError('Unsupported >8 decimal digits in ' + name)
    return value


def load(paths, symbol='BTCUSDT', *, allow_gaps=False, max_bars=50000):
    if type(max_bars) is not int or max_bars < 1:
        raise ValueError('max_bars must be a positive integer')
    shards = validated_shards(paths, symbol)
    candles = []
    gaps = 0
    last_sec = None
    for path, meta in shards:
        file_count = 0
        first_sec = None
        with path.open(newline='') as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not FIELDS.issubset(reader.fieldnames):
                raise ValueError('Invalid canonical CSV columns: ' + str(path))
            for row in reader:
                try:
                    stamp = row['timestamp']
                    if not re.fullmatch(r'[0-9]+', stamp):
                        raise ValueError('Invalid integer timestamp')
                    second = int(stamp)
                    if second < 946684800 or second % 60:
                        raise ValueError('Expected UTC minute-open timestamp in seconds')
                    values = {k: decimal_value(row[k], k) for k in FIELDS - {'timestamp'}}
                except (KeyError, TypeError) as exc:
                    raise ValueError('Malformed canonical CSV row') from exc
                if (values['high'] < max(values['open'], values['close'], values['low'])
                        or values['low'] > min(values['open'], values['close'])):
                    raise ValueError('Inconsistent OHLC prices')
                if last_sec is not None:
                    diff = second - last_sec
                    if diff <= 0 or diff % 60:
                        raise ValueError('Overlapping or unordered candles')
                    if diff > 60:
                        gaps += diff // 60 - 1
                        if not allow_gaps:
                            raise ValueError('Missing minute candles; pass --allow-gaps for explicit observation-only replay')
                last_sec = second
                first_sec = second if first_sec is None else first_sec
                candles.append(Candle(second, **values))
                file_count += 1
                if len(candles) > max_bars:
                    raise ValueError('Memory budget exceeded: raise --max-bars explicitly or use smaller shards')
        if (file_count != meta['rows'] or first_sec * 1000 != meta.get('first_open_ms')
                or last_sec * 1000 != meta.get('last_open_ms')):
            raise ValueError('Sidecar row count or timestamp bounds mismatch: ' + str(path))
    return candles, gaps, [{'path': str(path), 'sha256': meta['sha256']} for path, meta in shards]


def replay(candles, symbol):
    """Run the Nautilus v2 event engine; verify causal feature parity, no orders."""
    from integrations.nautilus_shadow import ShadowDigest, from_candles
    expected_features = from_candles(candles)
    try:
        installed = importlib.metadata.version('nautilus_trader')
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError('Missing experimental Nautilus wheel; use isolated Python 3.13 env') from exc
    if installed != VERSION:
        raise RuntimeError(f'Expected nautilus_trader=={VERSION}; got {installed}. Use an isolated Python 3.13 environment.')
    from nautilus_trader.backtest import BacktestEngine
    from nautilus_trader.common import LogLevel
    from nautilus_trader.config import BacktestEngineConfig, LoggerConfig, StrategyConfig
    from nautilus_trader.execution import MakerTakerFeeModel
    from nautilus_trader.model import (AccountType, Bar, BarType, Currency, CurrencyPair,
                                      InstrumentId, Money, OmsType, Price, Quantity, Symbol, Venue)
    from nautilus_trader.trading import Strategy

    base = Currency.from_str(SYMBOLS[symbol])
    quote = Currency.from_str('USDT')
    instrument_id = InstrumentId.from_str(f'{symbol}.RESEARCH')
    bar_type = BarType.from_str(f'{symbol}.RESEARCH-1-MINUTE-LAST-EXTERNAL')
    instrument = CurrencyPair(instrument_id=instrument_id, raw_symbol=Symbol(symbol),
                              base_currency=base, quote_currency=quote,
                              price_precision=8, size_precision=8,
                              price_increment=Price.from_str('0.00000001'),
                              size_increment=Quantity.from_str('0.00000001'),
                              ts_event=0, ts_init=0,
                              lot_size=Quantity.from_str('0.00000001'),
                              margin_init=Decimal('0.03'), margin_maint=Decimal('0.03'))

    class ObserveOnly(Strategy):
        def __init__(self):
            super().__init__(StrategyConfig())
            self.seen = 0
            self.last_ts = 0
            self.shadow = ShadowDigest()

        def on_start(self):
            self.subscribe_bars(bar_type)

        def on_bar(self, bar):
            if bar.ts_init <= self.last_ts:
                raise ValueError('Nautilus dispatched bars out of order')
            self.last_ts = bar.ts_init
            self.seen += 1
            self.shadow.accept(
                int(bar.ts_init // 1_000_000_000) - 60,
                open=bar.open, high=bar.high, low=bar.low,
                close=bar.close, volume=bar.volume,
            )

    build_start = time.perf_counter()
    bars = [Bar(bar_type=bar_type,
                open=Price.from_str(f'{c.open:.8f}'), high=Price.from_str(f'{c.high:.8f}'),
                low=Price.from_str(f'{c.low:.8f}'), close=Price.from_str(f'{c.close:.8f}'),
                volume=Quantity.from_str(f'{c.volume:.8f}'),
                ts_event=c.close_ns, ts_init=c.close_ns) for c in candles]
    event_build_s = time.perf_counter() - build_start
    engine = BacktestEngine(BacktestEngineConfig(logging=LoggerConfig(stdout_level=LogLevel.ERROR)))
    observer = ObserveOnly()
    try:
        venue = Venue('RESEARCH')  # Deliberately NOT BINANCE; no live adapter
        engine.add_venue(venue=venue, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
                         base_currency=None, starting_balances=[Money(1000, quote)],
                         fee_model=MakerTakerFeeModel(maker_rate=Decimal('0'), taker_rate=Decimal('0')))
        engine.add_instrument(instrument)
        engine.add_data(bars)
        engine.add_strategy(observer)
        run_start = time.perf_counter()
        engine.run()
        engine_run_s = time.perf_counter() - run_start
        if observer.seen != len(candles) or observer.last_ts != candles[-1].close_ns:
            raise ValueError('Nautilus replay parity failure: missing/out-of-order bars')
        actual_features = observer.shadow.result()
        if actual_features != expected_features:
            raise ValueError('Nautilus feature parity failure: causal input differs from legacy engine')
        return {'nautilus_engine_executed': True, 'nautilus_version': installed,
                'dispatched_bars': observer.seen,
                'native_event_build_seconds': round(event_build_s, 6),
                'native_run_seconds': round(engine_run_s, 6),
                'native_dispatched_bars_per_second': round(observer.seen / engine_run_s, 2) if engine_run_s > 0 else None,
                **actual_features}
    finally:
        engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', nargs='+', type=Path, required=True)
    parser.add_argument('--symbol', choices=sorted(SYMBOLS), default='BTCUSDT')
    parser.add_argument('--mode', choices=('audit', 'replay'), default='audit')
    parser.add_argument('--allow-gaps', action='store_true')
    parser.add_argument('--max-bars', type=int, default=50000)
    args = parser.parse_args(argv)
    parse_start = time.perf_counter()
    data, gaps, sources = load(args.files, args.symbol, allow_gaps=args.allow_gaps, max_bars=args.max_bars)
    parse_seconds = time.perf_counter() - parse_start
    result = {'mode': args.mode, 'approved': False, 'real_orders': False, 'paper_orders': False,
              'symbol': args.symbol, 'source_venue': 'binance', 'simulation_venue': 'RESEARCH',
              'bars': len(data), 'missing_minutes': gaps, 'sources': sources,
              'source_parse_seconds': round(parse_seconds, 6),
              'first_open_s': data[0].open_second, 'last_close_ns': data[-1].close_ns,
              'timestamp_rule': 'one-minute Binance open UTC seconds mapped to close UTC nanoseconds',
              'nautilus_engine_executed': False}
    if args.mode == 'replay':
        result.update(replay(data, args.symbol))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
