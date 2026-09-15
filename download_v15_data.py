"""Resumable public data acquisition. Raw data stays outside Git."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile
from engine_v1.dataset import candles, sha256
from engine_v1.operations import atomic_json

FIELDS = ['timestamp', 'open', 'high', 'low', 'close', 'volume']


def fetch_file(url, path, limit=100 * 1024 * 1024):
    """Bounded read, timeout, retries and disk reserve. Never retain a partial file."""
    path = Path(path)
    if shutil.disk_usage(path.parent).free < limit + 1024 ** 3:
        raise OSError('Insufficient disk space: retain at least 1 GiB reserve')
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'Futures-BOT-research/1.5'})
            with urlopen(request, timeout=10) as response, path.open('wb') as output:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > limit:
                        raise ValueError('Source response exceeded size limit')
                    output.write(block)
            return
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            path.unlink(missing_ok=True)
            if isinstance(error, HTTPError) and error.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            delay = 2 ** attempt
            if isinstance(error, HTTPError):
                retry = error.headers.get('Retry-After', '')
                if retry.isdigit():
                    delay = max(delay, min(30, int(retry)))
            time.sleep(delay)
        except Exception:
            path.unlink(missing_ok=True)
            raise


def coinbase_rows(payload, start, end):
    if not isinstance(payload, list):
        raise ValueError('Invalid Coinbase response')
    found = {}
    for row in payload:
        if len(row) != 6:
            raise ValueError('Invalid Coinbase candle')
        stamp, low, high, opening, close, volume = row
        stamp = int(stamp)
        if not start <= stamp < end:
            continue
        normalized = [stamp, str(opening), str(high), str(low), str(close), str(volume)]
        if stamp in found and found[stamp] != normalized:
            raise ValueError('Conflicting source candles')
        found[stamp] = normalized
    return [found[stamp] for stamp in sorted(found)]


def save_shard(path, rows, source, venue, symbol, requested_range=None):
    tmp = path.with_suffix('.partial')
    try:
        with tmp.open('w', newline='') as handle:
            writer = csv.writer(handle)
            writer.writerow(FIELDS)
            writer.writerows(rows)
        count = gaps = 0
        first = last = None
        for row in candles([tmp]):
            stamp = row['timestamp']
            if last is not None:
                gaps += (stamp - last) // 60000 - 1
            first = stamp if first is None else first
            last = stamp
            count += 1
        if not count:
            raise ValueError('Empty source shard; no checkpoint written')
        metadata = {'venue': venue, 'symbol': symbol, 'timeframe_ms': 60000,
                    'source': source, 'rows': count, 'missing_internal_minutes': gaps,
                    'first_open_ms': first, 'last_open_ms': last,
                    'sha256': sha256(tmp), 'bytes': tmp.stat().st_size,
                    'retrieved_utc': datetime.now(timezone.utc).isoformat()}
        if requested_range is not None:
            start_ms, end_ms = requested_range
            if first < start_ms or last >= end_ms:
                raise ValueError('Source returned a candle outside its requested shard')
            metadata.update({'requested_start_ms': start_ms, 'requested_end_ms': end_ms,
                             'missing_minutes': (end_ms - start_ms) // 60000 - count})
        tmp.replace(path)
        atomic_json(path.with_suffix('.json'), metadata)
    finally:
        tmp.unlink(missing_ok=True)


def verified(path):
    meta_path = path.with_suffix('.json')
    if not path.exists() or not meta_path.exists():
        return False
    meta = json.loads(meta_path.read_text())
    if sha256(path) != meta['sha256'] or path.stat().st_size != meta['bytes']:
        raise ValueError('Existing shard failed integrity check: ' + str(path))
    return True


def binance(root, symbol, start, end):
    current = start.replace(day=1)
    if start != current or end.day != 1:
        raise ValueError('Binance monthly range must use first-of-month dates')
    while current < end:
        month = current.strftime('%Y-%m')
        path = root / f'binance-{symbol}-{month}.csv'
        url = f'https://data.binance.vision/data/spot/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip'
        if not verified(path):
            archive_path = root / 'download.zip.partial'
            checksum_path = root / 'checksum.partial'
            try:
                fetch_file(url + '.CHECKSUM', checksum_path, 4096)
                fetch_file(url, archive_path)
                if sha256(archive_path) != checksum_path.read_text().split()[0]:
                    raise ValueError('Published archive checksum mismatch')
                with zipfile.ZipFile(archive_path) as archive:
                    name = f'{symbol}-1m-{month}.csv'
                    if archive.getinfo(name).file_size > 512 * 1024 * 1024:
                        raise ValueError('Unexpected archive expansion')
                    with archive.open(name) as binary:
                        def normalized():
                            for row in csv.reader(io.TextIOWrapper(binary)):
                                stamp = int(row[0])
                                yield [stamp // (1000000 if stamp > 10 ** 14 else 1000), *row[1:6]]
                        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
                        save_shard(path, normalized(), url, 'binance', symbol,
                                   (int(current.timestamp()*1000), int(next_month.timestamp()*1000)))
            finally:
                archive_path.unlink(missing_ok=True)
                checksum_path.unlink(missing_ok=True)
        print(path, 'verified', flush=True)
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


def coinbase(root, symbol, start, end):
    current = start
    while current < end:
        stop = min(current + timedelta(days=1), end)
        path = root / f'coinbase-{symbol}-{current:%Y-%m-%d}.csv'
        if not verified(path):
            def normalized():
                page = current
                while page < stop:
                    page_end = min(page + timedelta(minutes=299), stop)
                    query = urlencode({'granularity': 60, 'start': page.isoformat(), 'end': page_end.isoformat()})
                    url = f'https://api.exchange.coinbase.com/products/{symbol}/candles?{query}'
                    tmp = root / 'response.partial'
                    try:
                        fetch_file(url, tmp, 1024 * 1024)
                        payload = json.loads(tmp.read_text(), parse_float=str)
                        yield from coinbase_rows(payload, int(page.timestamp()), int(page_end.timestamp()))
                    finally:
                        tmp.unlink(missing_ok=True)
                    page = page_end
                    time.sleep(.5)
            save_shard(path, normalized(), 'https://api.exchange.coinbase.com/products/' + symbol + '/candles', 'coinbase', symbol,
                       (int(current.timestamp()*1000), int(stop.timestamp()*1000)))
        print(path, 'verified', flush=True)
        current = stop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['binance', 'coinbase'], required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True, help='Exclusive UTC date')
    parser.add_argument('--root', type=Path, default=Path('data/market'))
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Z0-9-]{3,24}', args.symbol):
        parser.error('Invalid symbol')
    start, end = [datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=timezone.utc) for s in (args.start, args.end)]
    if start >= end or end > datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0):
        parser.error('Use a nonempty range of completed UTC days')
    args.root.mkdir(parents=True, exist_ok=True)
    from engine_v1.operations import process_lock
    with process_lock(args.root / 'download.lock'):
        globals()[args.source](args.root, args.symbol, start, end)


if __name__ == '__main__':
    main()
