"""Validate fixed paired research reports before declaring a batch complete."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def read_json(path):
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError('Non-finite research value')
        if isinstance(item, dict):
            for v in item.values(): finite(v)
        elif isinstance(item, list):
            for v in item: finite(v)
    finite(value)
    return value, hashlib.sha256(raw).hexdigest()


def validate_report(path, month, backend, audit_hashes):
    """Check identity and internal consistency, not economic validity."""
    try:
        report, digest = read_json(path)
        protocol, protocol_digest = read_json(Path(path).with_suffix('.protocol.json'))
        if report['approved'] is not False or report['pnl'] is not None:
            raise ValueError('Expected unapproved research without P&L')
        if report['protocol'] != protocol:
            raise ValueError('Report differs from saved protocol')
        expected = dict(symbol='ETHUSDT', start=f'2026-{month-2:02d}-01',
                        reserve_from='2026-09-01', backend=backend,
                        horizon_minutes=15, alpha=10)
        for key, value in expected.items():
            if protocol[key] != value:
                raise ValueError('Unexpected protocol field: '+key)
        for key, m in [('train_end_ms', month-1), ('calibration_end_ms', month),
                       ('test_end_ms', month+1)]:
            expected_ms = int(datetime(2026, m, 1, tzinfo=timezone.utc).timestamp()*1000)
            if protocol[key] != expected_ms:
                raise ValueError('Unexpected split boundary')
        for name, sha in audit_hashes.items():
            if protocol['input_sha256'].get(name) != sha:
                raise ValueError('Audit fingerprint mismatch')
        summary = report['summary']
        counts = summary['paired_rows']
        if set(counts) != {'train', 'calibration', 'test'} or any(
                type(n) is not int or n < 100 for n in counts.values()):
            raise ValueError('Invalid paired row counts')
        names = {'candles_only', 'candles_plus_flow'}
        for field in ('test_rmse_log_bps', 'test_spearman'):
            if set(summary[field]) != names:
                raise ValueError('Unexpected model set')
        if set(report['rankings']) != names:
            raise ValueError('Unexpected ranking model set')
        def number(value):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Expected finite numeric metric')
            return value
        zero = number(summary['zero_rmse_log_bps'])
        if zero < 0: raise ValueError('Negative RMSE')
        for name in names:
            ranking = report['rankings'][name]
            rmse = number(summary['test_rmse_log_bps'][name])
            rho = summary['test_spearman'][name]
            if rmse < 0 or (rho is not None and abs(number(rho)) > 1):
                raise ValueError('Invalid metric range')
            if (rmse != ranking['rmse_log_bps'] or rho != ranking['spearman']
                    or zero != ranking['zero_rmse_log_bps_same_rows']):
                raise ValueError('Summary disagrees with ranking')
            buckets = ranking['buckets']
            if not buckets or any(type(b['count']) is not int or b['count'] < 0 for b in buckets):
                raise ValueError('Invalid bucket counts')
            if sum(b['count'] for b in buckets) != counts['test']:
                raise ValueError('Bucket counts disagree with test rows')
        difference = summary['test_rmse_log_bps']['candles_plus_flow'] - summary['test_rmse_log_bps']['candles_only']
        if not math.isclose(number(summary['flow_minus_candle_rmse_log_bps']), difference,
                            rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError('Incorrect paired RMSE difference')
        return {'file': Path(path).name, 'sha256': digest,
                'protocol_sha256': protocol_digest, 'month': month, 'backend': backend}
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError('Malformed paired research report') from error
