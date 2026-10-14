"""Bounded public funding-history acquisition, separate from strategy execution."""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode

from download_v15_data import fetch_file
from engine_v1.dataset import sha256
from engine_v1.operations import process_lock

ENDPOINT = 'https://fapi.binance.com/fapi/v1/fundingRate'
LIMIT = 1000


def timestamp(day):
    return int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp())*1000


def validate_page(payload, symbol, cursor, end):
    if not isinstance(payload, list) or len(payload) > LIMIT:
        raise ValueError('Invalid funding response or page size')
    result = []
    previous = cursor-1
    for row in payload:
        if not isinstance(row, dict) or row.get('symbol') != symbol:
            raise ValueError('Funding symbol/schema mismatch')
        t = row.get('fundingTime')
        if type(t) is not int or not previous < t < end or t < cursor:
            raise ValueError('Funding times out of bounds, duplicated or unordered')
        if not isinstance(row.get('fundingRate'), str):
            raise ValueError('Funding rate must be a decimal string')
        rate = Decimal(row['fundingRate'])
        if not rate.is_finite():
            raise ValueError('Nonfinite funding rate')
        mark = row.get('markPrice')
        if mark not in (None, ''):
            if not isinstance(mark, str) or not Decimal(mark).is_finite() or Decimal(mark) <= 0:
                raise ValueError('Invalid funding mark price')
        result.append({'symbol': symbol, 'funding_time_ms': t,
                       'funding_rate': row['fundingRate'], 'mark_price': mark or None})
        previous = t
    return result


def download(symbol, start, end, reserve, output):
    if not re.fullmatch(r'[A-Z0-9]{3,24}', symbol) or not 1 <= (end-start).days <= 7:
        raise ValueError('Require valid symbol and 1–7 days, end exclusive')
    if end > reserve or end > datetime.now(timezone.utc).date():
        raise ValueError('Range crosses reserve or incomplete UTC day')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with process_lock(str(output)+'.lock'):
        if output.exists() or output.is_symlink():
            raise ValueError('Output exists; preserve it and choose a new path')
        with tempfile.TemporaryDirectory(prefix='funding-', dir=output.parent) as temp:
            stage = Path(temp)/'publish'
            stage.mkdir()
            cursor, stop = timestamp(start), timestamp(end)
            records, pages = [], []
            exhausted = False
            for n in range(8):
                url = ENDPOINT+'?'+urlencode(dict(symbol=symbol, startTime=cursor,
                                                 endTime=stop-1, limit=LIMIT))
                path = stage/f'page-{n:02d}.json'
                print(f'[funding] fetching page {n+1}/8', flush=True)
                fetch_file(url, path, limit=1024**2)
                page = validate_page(json.loads(path.read_text()), symbol, cursor, stop)
                pages.append({'file': path.name, 'url': url, 'sha256': sha256(path),
                              'bytes': path.stat().st_size, 'records': len(page)})
                records.extend(page)
                if len(page) < LIMIT or page[-1]['funding_time_ms'] == stop-1:
                    exhausted = True
                    break
                cursor = page[-1]['funding_time_ms']+1
            if not exhausted:
                raise ValueError('Funding page budget exhausted; no dataset published')
            if not records:
                raise ValueError('No funding records returned; completeness unknown')
            normalized = stage/'funding.json'
            normalized.write_text(json.dumps(records, indent=2)+'\n')
            gaps = sorted(set(b['funding_time_ms']-a['funding_time_ms']
                              for a, b in zip(records, records[1:])))
            report = {'approved': False, 'venue': 'binance_usdm', 'kind': 'funding_history',
                      'symbol': symbol, 'start': str(start), 'end_exclusive': str(end),
                      'reserve_from': str(reserve), 'records': len(records),
                      'first_funding_ms': records[0]['funding_time_ms'],
                      'last_funding_ms': records[-1]['funding_time_ms'],
                      'observed_intervals_ms': gaps,
                      'missing_mark_prices': sum(r['mark_price'] is None for r in records),
                      'api_pagination_exhausted': True, 'schedule_coverage_verified': False,
                      'funding_sha256': sha256(normalized), 'pages': pages,
                      'retrieved_utc': datetime.now(timezone.utc).isoformat(),
                      'runner_sha256': sha256(Path(__file__)),
                      'limitations': ['API pagination exhaustion does not prove historical schedule completeness.',
                                      'No fixed eight-hour schedule is assumed; gaps require review.',
                                      'Raw API responses have local hashes, not exchange archive checksums.',
                                      'Realized funding is not a forecast available before settlement.',
                                      'No position cash flows, fees, trading or strategy approval.']}
            (stage/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
            os.rename(stage, output)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol', default='ETHUSDT')
    p.add_argument('--start', type=date.fromisoformat, required=True)
    p.add_argument('--end', type=date.fromisoformat, required=True)
    p.add_argument('--reserve-from', type=date.fromisoformat, default=date(2026, 9, 1))
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(download(a.symbol, a.start, a.end, a.reserve_from, a.output_dir), indent=2))


if __name__ == '__main__':
    main()
