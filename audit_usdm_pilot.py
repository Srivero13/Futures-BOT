"""Revalidate a saved futures pilot and its timestamp alignment to spot candles."""
import argparse
import csv
from datetime import date
import json
from pathlib import Path
import re

from download_usdm_pilot import FIELDS, validate_archive
from engine_v1.dataset import candles, sha256
from research_cross_asset import verify


def audit(pilot, spot, symbol, day, reserve):
    if not re.fullmatch(r'[A-Z0-9]{3,24}', symbol) or day >= reserve:
        raise ValueError('Invalid symbol or reserved date')
    pilot, spot = Path(pilot), Path(spot)
    stem = f'{symbol}-1m-{day}'
    archive = pilot / (stem + '.zip')
    checksum = pilot / (stem + '.zip.CHECKSUM')
    converted = pilot / f'binance-usdm-{symbol}-{day}.csv'
    sidecar = converted.with_suffix('.json')
    paths = [archive, checksum, converted, sidecar, spot, spot.with_suffix('.json')]
    before = {str(p.resolve()): sha256(p) for p in paths}
    meta = json.loads(sidecar.read_text())
    expected = {'venue': 'binance_usdm', 'market': 'usd_m_futures', 'symbol': symbol,
                'date': str(day), 'timeframe_ms': 60000, 'source_timestamp_unit': 'ms',
                'rows': 1440, 'sha256': sha256(converted), 'bytes': converted.stat().st_size,
                'archive_sha256': sha256(archive), 'checksum_sha256': sha256(checksum),
                'source_url': f'https://data.binance.vision/data/futures/um/daily/klines/{symbol}/1m/{stem}.zip'}
    if any(meta.get(k) != v for k, v in expected.items()) or meta.get('approved') is not False:
        raise ValueError('Futures metadata or saved file integrity mismatch')
    if date.fromisoformat(meta['reserve_from']) > reserve or day >= date.fromisoformat(meta['reserve_from']):
        raise ValueError('Saved reserve boundary mismatch')
    if archive.stat().st_size > 8 * 1024**2 or checksum.stat().st_size > 4096:
        raise ValueError('Saved archive/checksum exceeds pilot bounds')
    raw_rows = validate_archive(archive, checksum, symbol, day)
    with converted.open(newline='') as f:
        reader = csv.reader(f)
        if next(reader, None) != FIELDS:
            raise ValueError('Converted CSV header mismatch')
        for raw in raw_rows:
            if next(reader, None) != list(map(str, raw)):
                raise ValueError('Converted CSV differs from source archive')
        if next(reader, None) is not None:
            raise ValueError('Unexpected extra converted rows')
    start, last = raw_rows[0][0]*1000, raw_rows[-1][0]*1000
    if (meta.get('first_open_ms'), meta.get('last_open_ms')) != (start, last):
        raise ValueError('Futures range metadata mismatch')
    # Verify the complete supplied spot shard, then select only the pilot day.
    from datetime import datetime, timezone
    reserve_ms = int(datetime.combine(reserve, datetime.min.time(), timezone.utc).timestamp())*1000
    verify([spot], symbol, reserve_ms)
    matched = []
    for row in candles([spot]):
        if start <= row['timestamp'] <= last:
            matched.append(row['timestamp'])
    if matched != [r[0]*1000 for r in raw_rows]:
        raise ValueError('Spot/futures day has missing or misaligned timestamps')
    after = {str(p.resolve()): sha256(p) for p in paths}
    if after != before:
        raise ValueError('Inputs changed during audit')
    return {'approved': False, 'symbol': symbol, 'date': str(day),
            'integrity_passed': True, 'archive_conversion_equal': True,
            'timestamp_alignment_passed': True, 'matched_minutes': len(matched),
            'inputs_sha256': before, 'audit_runner_sha256': sha256(Path(__file__)),
            'archive_validator_sha256': sha256(Path(__file__).with_name('download_usdm_pilot.py')),
            'recorded_downloader_sha256': meta.get('runner_sha256'),
            'limitations': ['Reuses the ingestion archive validator; not an independent parser implementation.',
                            'Spot provenance is checked against its local sidecar; raw spot archives are not reverified.',
                            'Matching candle timestamps do not establish simultaneous executable prices.',
                            'No funding, fees, price-convergence test, strategy evaluation or P&L.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pilot-dir', type=Path, required=True)
    p.add_argument('--spot-file', type=Path, required=True)
    p.add_argument('--symbol', default='ETHUSDT')
    p.add_argument('--date', type=date.fromisoformat, required=True)
    p.add_argument('--reserve-from', type=date.fromisoformat, default=date(2026, 9, 1))
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists() or args.output.is_symlink():
        p.error('Output exists; preserve it and choose a new report path')
    print('[usdm-audit] verifying saved archives, conversion and spot alignment', flush=True)
    report = audit(args.pilot_dir, args.spot_file, args.symbol, args.date, args.reserve_from)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents replacing an input or an existing report.
    with args.output.open('x') as f:
        f.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
