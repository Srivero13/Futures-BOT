"""One-command registered WBC01-F01 evaluation; no interim performance or orders."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from engine_v1.dataset import candles, sha256
from engine_v1.research_artifacts import read_json
from register_weekly_btc_forward import PLAN, register
from research_weekly_btc import build_schedule, simulate
from diagnose_weekly_btc_risk import replay

PLAN_HASH = 'ce74905aca4ae80d0463f46941d1cf98eb528e164a6a65e8645599d9ea73dc4d'
ROOT = Path(__file__).resolve().parent
FROZEN_CODE = ('research_weekly_btc.py', 'diagnose_weekly_btc_risk.py',
               'engine_v1/dataset.py', 'engine_v1/research_artifacts.py')


def preflight(registration_path, now=None):
    now = now or datetime.now(timezone.utc)
    registration, digest = read_json(registration_path)
    plan, plan_hash = read_json(PLAN)
    if plan_hash != PLAN_HASH or registration.get('evaluation_protocol_sha256') != PLAN_HASH or registration.get('evaluation_protocol') != plan:
        raise ValueError('Registered forward protocol changed')
    if registration.get('approved') is not False or registration.get('experiment') != 'WBC01-F01' or registration.get('status') != 'registered_pending_future_data':
        raise ValueError('Unexpected registration identity')
    registered = datetime.fromisoformat(registration['registered_utc'])
    if now.tzinfo is None or registered.tzinfo is None or registered > now:
        raise ValueError('Invalid registration clock')
    rebuilt = register(registration['snapshot'], now=registered)
    for key in ('snapshot_manifest_sha256','frozen_files','evaluation_protocol_sha256','evaluation_protocol'):
        if rebuilt[key] != registration[key]:
            raise ValueError(f'Registration binding mismatch: {key}')
    for name in FROZEN_CODE:
        if sha256(ROOT/name) != registration['frozen_files'][name]:
            raise ValueError(f'Frozen implementation changed: {name}')
    end = datetime.fromisoformat(plan['evaluation_end_exclusive_utc'])
    return registration, digest, dict(approved=False, experiment='WBC01-F01',
        registration_verified=True, frozen_implementation_verified=True,
        evaluation_start_utc=plan['evaluation_start_utc'], evaluation_end_exclusive_utc=end.isoformat(),
        status='window_elapsed_data_validation_required' if now >= end else 'waiting_for_fixed_window_end',
        market_data_read=False, background_job_started=False)


def evaluate(registration_path, paths, now=None):
    registration, digest, readiness = preflight(registration_path, now)
    if readiness['status'] != 'window_elapsed_data_validation_required':
        raise ValueError('Fixed forward window has not ended; interim evaluation disabled')
    plan = registration['evaluation_protocol']
    start = int(datetime.fromisoformat(plan['evaluation_start_utc']).timestamp()*1000)
    end = int(datetime.fromisoformat(plan['evaluation_end_exclusive_utc']).timestamp()*1000)
    warmup = int(datetime.fromisoformat(plan['warmup_start_utc']).timestamp()*1000)
    paths = [Path(p).resolve() for p in paths]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError('Require unique candle shards')
    sources = {}; ordered = []
    for path in paths:
        if path.suffix != '.csv':
            raise ValueError('Require canonical CSV shards')
        meta_path = path.with_suffix('.json')
        meta, meta_hash = read_json(meta_path)
        first, last = meta.get('first_open_ms'), meta.get('last_open_ms')
        if type(first) is not int or type(last) is not int or first > last:
            raise ValueError('Missing shard interval')
        # Monthly October/April shards may include unscored edge minutes, but
        # September and unrelated shards must not enter this evaluation.
        earliest = int(datetime(2026,10,1,tzinfo=timezone.utc).timestamp()*1000)
        latest = int(datetime(2027,5,1,tzinfo=timezone.utc).timestamp()*1000)
        if first < earliest or last >= latest or last < warmup or first >= end:
            raise ValueError('Shard outside forward/warmup scope')
        candle_hash = sha256(path)
        if (meta.get('venue'),meta.get('symbol'),meta.get('timeframe_ms'),meta.get('sha256')) != ('binance','BTCUSDT',60000,candle_hash):
            raise ValueError('Candle provenance mismatch')
        sources[str(path)] = candle_hash; sources[str(meta_path)] = meta_hash
        ordered.append((first,path))
    paths = [p for _,p in sorted(ordered)]
    decisions, events = build_schedule(candles(paths), start=start, end=end)
    scenarios = {name:simulate(events,impact,hold=hold) for name,impact,hold in
                 [('base','2',False),('stress','3',False),('buy_and_hold','2',True)]}
    risk = replay(candles(paths), scenarios, start=start, end=end)
    failures = []
    for value, label in ((scenarios['base']['net_pnl'],'Nonpositive base net'),
                         (scenarios['stress']['net_pnl'],'Nonpositive stress net'),
                         (scenarios['base']['net_excluding_best_trade'],'Nonpositive base net excluding best trade')):
        if value <= 0:
            failures.append(label)
    if sha256(registration_path) != digest or any(sha256(p) != h for p,h in sources.items()):
        raise ValueError('Inputs changed during evaluation')
    preflight(registration_path, now)
    return dict(approved=False, experiment='WBC01-F01', registration_sha256=digest,
        evaluation_protocol_sha256=PLAN_HASH, sources=sources, decisions=decisions,
        scenarios=scenarios, risk=risk, cash_baseline_net_pnl='0',
        summary=dict(closed_trades=scenarios['base']['closed_trades'],
            net_pnl=scenarios['base']['net_pnl'],stress_net_pnl=scenarios['stress']['net_pnl'],
            buy_and_hold_net_pnl=scenarios['buy_and_hold']['net_pnl'],
            net_excluding_best_trade=scenarios['base']['net_excluding_best_trade'],
            economic_screen_failures=failures,
            status='economic_screen_failed' if failures else 'economic_screen_passed_further_review_only'),
        code_sha256={p:sha256(ROOT/p) for p in (*FROZEN_CODE,'register_weekly_btc_forward.py','evaluate_weekly_btc_forward.py')},
        limitations=plan['limitations']+[
            'No automatic approval, statistical significance or sufficient-sample claim.',
            'Full source shards may contain unscored October/April edge minutes.',
            'Local source hashes are consistency checks, not independent exchange authenticity proofs.',
            'No scheduler or live paper execution; this command performs historical reference replay.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration',type=Path,required=True)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--files',nargs='+')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.check:
        if args.files or args.output:
            parser.error('--check does not accept market files or output')
        print(json.dumps(preflight(args.registration)[2],indent=2))
        return
    if not args.files or not args.output:
        parser.error('Evaluation requires --files and --output')
    if args.output.exists() or args.output.is_symlink():
        parser.error('Use a new output path')
    result = evaluate(args.registration,args.files)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result,f,default=str,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(result['summary'],default=str,indent=2))


if __name__ == '__main__': main()
