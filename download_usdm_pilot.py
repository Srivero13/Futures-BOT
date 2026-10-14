"""One-day public USD-M candle acquisition; no trading or model approval."""
import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from download_v15_data import fetch_file
from engine_v1.dataset import sha256
from engine_v1.operations import process_lock

FIELDS = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
HEADER = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
          'quote_volume', 'count', 'taker_buy_volume', 'taker_buy_quote_volume', 'ignore']


def validate_archive(archive, checksum, symbol, day):
    name = f'{symbol}-1m-{day.isoformat()}'
    tokens = checksum.read_text().strip().split()
    if (len(tokens) != 2 or not re.fullmatch(r'[0-9a-fA-F]{64}', tokens[0])
            or tokens[1].lstrip('*') != name + '.zip'
            or sha256(archive) != tokens[0].lower()):
        raise ValueError('Archive checksum or filename mismatch')
    start = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp()) * 1000
    result = []
    with zipfile.ZipFile(archive) as z:
        if z.namelist() != [name + '.csv']:
            raise ValueError('Unexpected archive members')
        member = z.getinfo(name + '.csv')
        if member.file_size > 8 * 1024 ** 2:
            raise ValueError('Expanded CSV exceeds 8 MiB')
        with z.open(member) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding='utf-8-sig', newline=''))
            for index, row in enumerate(reader):
                if index == 0 and row == HEADER:
                    continue
                if len(row) != 12 or len(result) >= 1440:
                    raise ValueError('Invalid candle count or schema')
                expected = start + len(result) * 60000
                if int(row[0]) != expected or int(row[6]) != expected + 59999:
                    raise ValueError('Missing, duplicate, unordered or non-millisecond candle')
                opening, high, low, close, volume = map(Decimal, row[1:6])
                if not all(x.is_finite() for x in (opening, high, low, close, volume)):
                    raise ValueError('Nonfinite OHLCV')
                if not (0 < low <= min(opening, close) <= max(opening, close) <= high and volume >= 0):
                    raise ValueError('Invalid OHLCV')
                result.append([expected // 1000, *row[1:6]])
    if len(result) != 1440:
        raise ValueError('Expected exactly 1440 complete minute candles')
    return result


def download(symbol, day, reserve, destination):
    if not re.fullmatch(r'[A-Z0-9]{3,24}', symbol):
        raise ValueError('Invalid symbol')
    if day >= reserve or day >= datetime.now(timezone.utc).date():
        raise ValueError('Date must precede reserve and current UTC day')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with process_lock(str(destination) + '.lock'):
        if destination.exists() or destination.is_symlink():
            raise ValueError('Output directory already exists; preserve it and choose a new path')
        with tempfile.TemporaryDirectory(prefix='usdm-pilot-', dir=destination.parent) as temp:
            stage = Path(temp) / 'publish'
            stage.mkdir()
            name = f'{symbol}-1m-{day.isoformat()}'
            url = f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/1m/{name}.zip'
            archive = stage / (name + '.zip')
            checksum = stage / (name + '.zip.CHECKSUM')
            print('[usdm-pilot] downloading checksum and bounded archive', flush=True)
            fetch_file(url + '.CHECKSUM', checksum, limit=4096)
            fetch_file(url, archive, limit=8 * 1024 ** 2)
            rows = validate_archive(archive, checksum, symbol, day)
            output = stage / f'binance-usdm-{symbol}-{day}.csv'
            with output.open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(FIELDS)
                writer.writerows(rows)
            metadata = {
                'approved': False, 'venue': 'binance_usdm', 'market': 'usd_m_futures',
                'symbol': symbol, 'date': str(day), 'timeframe_ms': 60000,
                'rows': len(rows), 'source_url': url, 'source_timestamp_unit': 'ms',
                'first_open_ms': rows[0][0] * 1000, 'last_open_ms': rows[-1][0] * 1000,
                'sha256': sha256(output), 'bytes': output.stat().st_size,
                'archive_sha256': sha256(archive), 'checksum_sha256': sha256(checksum),
                'runner_sha256': sha256(Path(__file__)), 'reserve_from': str(reserve),
                'retrieved_utc': datetime.now(timezone.utc).isoformat(),
                'limitations': ['Trade-price candles, not executable quotes or mark prices.',
                                'Funding, account fees and contract rules are not included.',
                                'One-day integrity pilot; not strategy or profitability evidence.']}
            output.with_suffix('.json').write_text(json.dumps(metadata, indent=2) + '\n')
            # All files become visible together; the cooperating writer lock prevents races.
            os.rename(stage, destination)
    return metadata


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol', default='ETHUSDT')
    p.add_argument('--date', type=date.fromisoformat, required=True)
    p.add_argument('--reserve-from', type=date.fromisoformat, default=date(2026, 9, 1))
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(download(args.symbol, args.date, args.reserve_from, args.output_dir), indent=2))


if __name__ == '__main__':
    main()
