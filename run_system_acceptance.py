"""Isolated paper-ledger lifecycle and public-feed acceptance. Never sends orders."""
import argparse
import json
from pathlib import Path

from doctor import check
from engine_v1.core import Portfolio, Quote, dec
from engine_v1.operations import atomic_json, backup_database
from report_paper_ledger import report
from restore_paper_ledger import restore

ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ledger_lifecycle(root):
    """Synthetic deterministic inputs in a new isolated directory, never live signals."""
    root = Path(root)
    root.mkdir(exist_ok=False)
    accounts = [dict(id='acceptance-btc',symbol='BTCUSDT',capital='1000',notional='100'),
                dict(id='acceptance-eth',symbol='ETHUSDT',capital='1000',notional='100')]
    def quotes(now):
        return {a['symbol']:Quote(a['symbol'],dec('100'),dec('100.01'),dec('100'),dec('100'),now,now) for a in accounts}
    entries = {a['id']:{'enter':True} for a in accounts}
    source = root/'synthetic.sqlite3'
    engine = Portfolio(source, accounts)
    try:
        engine.process(quotes(1000),entries,1000,event_id='paused',allow_entries=False)
        require(report(source)['trade_events']==0,'Pause allowed an entry')
        engine.process(quotes(2000),entries,2000,event_id='entry')
        before = engine.states()
        require(all(dec(a['qty'])>0 for a in before),'Both virtual accounts must open')
        engine.process(quotes(2000),entries,2000,event_id='entry')
        require(engine.states()==before,'Duplicate event changed account state')
        require(report(source)['trade_events']==2,'Duplicate event created trades')
        require(report(source)['reconciled'],'Open ledger failed reconciliation')
        # Online backup must preserve committed state while the source is open.
        backup_database(source,root/'backup.sqlite3')
    finally:
        engine.close()
    restore(root/'backup.sqlite3',root/'restored.sqlite3')
    restored = Portfolio(root/'restored.sqlite3',accounts)
    try:
        require(restored.states()==before,'Restored open positions differ')
        restored.process(quotes(2000),entries,2000,event_id='entry')
        require(restored.states()==before,'Restored duplicate protection failed')
        restored.process(quotes(3000),{},3000,event_id='flatten',allow_entries=False,force_exit=True)
        require(all(dec(a['qty'])==0 for a in restored.states()),'Flatten left a virtual position')
        final = report(root/'restored.sqlite3')
        require(final['reconciled'] and final['trade_events']==4,'Closed ledger failed reconciliation')
    finally:
        restored.close()
    atomic_json(root/'reconciliation.json',final)
    return dict(passed=True,synthetic=True,accounts=2,trade_events=4,
        checks=['pause_blocks_entries','two_account_entries','duplicate_protection',
                'online_backup','restore_open_positions','restored_duplicate_protection',
                'flatten_while_paused','financial_reconciliation'],
        scope='Synthetic engineering control only; no model approval, market fills or profitability evidence.')


def assess_feed(result, health, seconds, symbols):
    checks = dict(
        observe_only=result.get('observe_only') is True and health.get('observe_only') is True,
        duration_completed=isinstance(result.get('duration_seconds'),(int,float)) and result['duration_seconds']>=seconds,
        messages_received=type(result.get('messages')) is int and result['messages']>0,
        clock_stable=result.get('clock_ok') is True and health.get('clock_ok') is True,
        no_recorded_errors=result.get('errors')=={} and health.get('errors')=={},
        stopped_cleanly=health.get('running') is False and health.get('connection_state')=='stopped',
        both_symbols_warmed=all(health.get('warm_candles',{}).get(s,0)>=21 for s in symbols),
        final_quotes_fresh=all(isinstance(health.get('quote_age_ms',{}).get(s),(int,float)) and
                              0<=health['quote_age_ms'][s]<=1000 for s in symbols))
    return dict(passed=all(checks.values()),checks=checks,
                failures=[k for k,v in checks.items() if not v],
                scope='Finite public-feed smoke test; final quote freshness is not continuous coverage or order latency.')


def run(output, seconds=1800, offline_only=False):
    output = Path(output).resolve()
    require(type(seconds) is int and 1800<=seconds<=21600,'Duration must be 1800–21600 seconds')
    output.mkdir(parents=True,exist_ok=False)
    result = dict(approved=False,real_orders=False,status='running',stage='doctor',
                  scope='Engineering acceptance only; strategy profitability and live execution remain unvalidated.')
    def save(): atomic_json(output/'acceptance.json',result)
    save()
    try:
        result['doctor'] = check(ROOT,output)
        require(result['doctor']['ready'],'Startup doctor failed; inspect acceptance.json')
        result['stage']='synthetic_ledger';save()
        print('[acceptance] isolated two-account ledger lifecycle',flush=True)
        result['ledger']=ledger_lifecycle(output/'synthetic-ledger')
        if offline_only:
            result.update(status='offline_checks_passed_feed_not_tested',stage='complete',engineering_checks_passed=False)
        else:
            from engine_v1.stream import stream
            result['stage']='public_feed';save()
            print(f'[acceptance] public observer for {seconds}s; no trading',flush=True)
            raw=stream(seconds,observe=True,health_path=output/'observe-health.json',progress_interval=5)
            atomic_json(output/'observation.json',raw)
            health=json.loads((output/'observe-health.json').read_text())
            cfg=json.loads((ROOT/'configs/v11-paper.json').read_text())
            result['feed']=assess_feed(raw,health,seconds,{a['symbol'] for a in cfg['accounts']})
            passed=result['feed']['passed']
            result.update(status='finite_engineering_checks_passed' if passed else 'feed_checks_failed',
                          stage='complete',engineering_checks_passed=passed)
    except BaseException as error:
        result.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',
                      error_type=type(error).__name__,engineering_checks_passed=False)
        save()
        raise
    save()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=1800)
    p.add_argument('--offline-only',action='store_true')
    a=p.parse_args()
    result=run(a.output_dir,a.seconds,a.offline_only)
    print(json.dumps(result,indent=2))
    return 0 if result.get('engineering_checks_passed') or a.offline_only else 2


if __name__=='__main__': raise SystemExit(main())
