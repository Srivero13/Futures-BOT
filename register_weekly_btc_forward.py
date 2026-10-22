"""Bind a prospective WBC01 evaluation plan to a verified development snapshot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from engine_v1.research_artifacts import read_json

PLAN = Path(__file__).parent / 'research_protocols/weekly_btc_forward_v1.json'
FILES = (
    'research_protocols/weekly_btc_control_v1.json',
    'research_weekly_btc.py', 'diagnose_weekly_btc_risk.py',
    'engine_v1/dataset.py', 'engine_v1/research_artifacts.py',
    'data/weekly-btc-WBC01-development.json', 'data/weekly-btc-WBC01-risk.json',
)


def register(snapshot, now=None):
    snapshot = Path(snapshot).resolve()
    now = now or datetime.now(timezone.utc)
    plan, plan_hash = read_json(PLAN)
    start = datetime.fromisoformat(plan['evaluation_start_utc'])
    if now.tzinfo is None or now >= start:
        raise ValueError('Registration must precede evaluation start; no backdating')
    manifest, manifest_hash = read_json(snapshot / 'manifest.json')
    if manifest.get('approved') is not False or manifest.get('experiment') != 'WBC01' or set(manifest.get('files', {})) != set(FILES):
        raise ValueError('Unexpected snapshot identity or file set')
    payloads = {}
    for name in FILES:
        path = snapshot / name
        if not path.resolve().is_relative_to(snapshot):
            raise ValueError('Snapshot path escapes root')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['files'][name]:
            raise ValueError(f'Snapshot hash mismatch: {name}')
        payloads[name] = data
    if manifest['files'][FILES[0]] != plan['rule_protocol_sha256']:
        raise ValueError('Different frozen strategy protocol')
    development = json.loads(payloads[FILES[-2]])
    risk = json.loads(payloads[FILES[-1]])
    for report in (development, risk):
        if report.get('approved') is not False or report.get('experiment') != 'WBC01':
            raise ValueError('Unexpected report identity')
        if report.get('protocol_sha256') != plan['rule_protocol_sha256']:
            raise ValueError('Report protocol mismatch')
    if development['summary']['screen_failures']:
        raise ValueError('Development screen failed')
    if risk['source_report_sha256'] != manifest['files'][FILES[-2]]:
        raise ValueError('Risk report/development mismatch')
    if set(risk['scenarios']) != {'base', 'stress', 'buy_and_hold'} or not all(s['terminal_reconciled'] is True for s in risk['scenarios'].values()):
        raise ValueError('Incomplete risk reconciliation')
    for report in (development, risk):
        for name, digest in report['code_sha256'].items():
            if manifest['files'].get(name) != digest:
                raise ValueError(f'Report code differs from snapshot: {name}')
    # Recheck files after reading, before declaring the registration complete.
    for name, data in payloads.items():
        if (snapshot / name).read_bytes() != data:
            raise ValueError('Snapshot changed during registration')
    if read_json(snapshot / 'manifest.json')[1] != manifest_hash or read_json(PLAN)[1] != plan_hash:
        raise ValueError('Manifest or plan changed during registration')
    return dict(approved=False, experiment='WBC01-F01', status='registered_pending_future_data',
                registered_utc=now.isoformat(), snapshot=str(snapshot),
                snapshot_manifest_sha256=manifest_hash, frozen_files=manifest['files'],
                evaluation_protocol_sha256=plan_hash, evaluation_protocol=plan,
                limitations=['Local clock and hashes are not a trusted timestamp authority.',
                             'No market data read and no evaluation performed.',
                             'No background collection or orders started.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Use a new output path')
    result = register(args.snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({k:result[k] for k in ('approved','experiment','status','registered_utc','evaluation_protocol_sha256')}, indent=2))
    print('Evaluation:', result['evaluation_protocol']['evaluation_start_utc'], 'to',
          result['evaluation_protocol']['evaluation_end_exclusive_utc'])


if __name__ == '__main__':
    main()
