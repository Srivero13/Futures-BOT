"""Acquire and audit at most seven consecutive development days; no trading."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import re

from audit_usdm_pilot import audit
from download_usdm_pilot import download
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json


def run(symbol, start, end, reserve, spot_root, output):
    days = (end-start).days
    if not re.fullmatch(r'[A-Z0-9]{3,24}', symbol) or not 1 <= days <= 7:
        raise ValueError('Require valid symbol and 1–7 days, end exclusive')
    if end > reserve or end > datetime.now(timezone.utc).date():
        raise ValueError('Batch crosses reserve or incomplete UTC day')
    spot_root, output = Path(spot_root), Path(output)
    dates = [start+timedelta(days=i) for i in range(days)]
    spots = [spot_root/f'binance-{symbol}-{day:%Y-%m}.csv' for day in dates]
    # Missing local prerequisites must fail before downloading or creating output.
    for spot in set(spots):
        if not spot.is_file() or not spot.with_suffix('.json').is_file():
            raise ValueError(f'Missing spot shard or sidecar: {spot}')
    output.mkdir(parents=True, exist_ok=False)
    status = {'approved': False, 'status': 'running', 'symbol': symbol,
              'start': str(start), 'end_exclusive': str(end), 'reserve_from': str(reserve),
              'requested_days': days, 'completed_days': [], 'active_day': None,
              'runner_sha256': sha256(Path(__file__)),
              'limitations': ['Acquisition/alignment only; no funding, fees or strategy evaluation.',
                              'Completed days remain available after failure; no automatic resume.',
                              'Status can remain running after abrupt process or power loss.']}
    status_path = output/'status.json'
    try:
        atomic_json(status_path, status)
        for i, (day, spot) in enumerate(zip(dates, spots), 1):
            status['active_day'] = str(day)
            atomic_json(status_path, status)
            print(f'[usdm-batch] day {i}/{days}: {day} downloading', flush=True)
            folder = output/str(day)
            download(symbol, day, reserve, folder)
            print(f'[usdm-batch] day {i}/{days}: auditing', flush=True)
            report = audit(folder, spot, symbol, day, reserve)
            if (report.get('approved') is not False or report.get('matched_minutes') != 1440
                    or not all(report.get(k) is True for k in
                               ('integrity_passed', 'archive_conversion_equal', 'timestamp_alignment_passed'))):
                raise ValueError('Day did not pass required audit checks')
            path = output/f'{day}-audit.json'
            atomic_json(path, report)
            status['completed_days'].append({'date': str(day), 'matched_minutes': 1440,
                                             'audit': path.name, 'sha256': sha256(path)})
            atomic_json(status_path, status)
            print(f'[usdm-batch] day {i}/{days}: verified 1440 minutes', flush=True)
        # Recheck all input/report hashes before publishing batch completion.
        for item in status['completed_days']:
            path = output/item['audit']
            if sha256(path) != item['sha256']:
                raise ValueError('Audit report changed during batch')
            for source, digest in json.loads(path.read_text())['inputs_sha256'].items():
                if sha256(source) != digest:
                    raise ValueError('Audited input changed during batch')
        status.update(status='complete', active_day=None, matched_minutes=days*1440)
        atomic_json(status_path, status)
    except BaseException as error:
        status.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                      error_type=type(error).__name__)
        try:
            atomic_json(status_path, status)
        except Exception as save_error:
            error.add_note(f'Could not save failure status: {type(save_error).__name__}')
        raise
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol', default='ETHUSDT')
    p.add_argument('--start', type=date.fromisoformat, required=True)
    p.add_argument('--end', type=date.fromisoformat, required=True)
    p.add_argument('--reserve-from', type=date.fromisoformat, default=date(2026, 9, 1))
    p.add_argument('--spot-root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(run(a.symbol, a.start, a.end, a.reserve_from, a.spot_root, a.output_dir), indent=2))


if __name__ == '__main__':
    main()
