"""Finite public Binance quote observation, with no execution clients."""
import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

SYMBOLS = ('BTCUSDT', 'ETHUSDT')


class Health:
    def __init__(self, now, wall):
        self.started = now
        self.wall = wall
        self.counts = dict.fromkeys(SYMBOLS, 0)
        self.last = {}
        self.max_gap_ms = dict.fromkeys(SYMBOLS, 0.0)
        self.stale_samples = 0
        self.recoveries = 0
        self.was_stale = False
        self.clock_ok = True
        self.invalid_quotes = 0

    def quote(self, symbol, now, bid, ask, bid_size, ask_size):
        if symbol not in self.counts or not (0 < bid <= ask and bid_size > 0 and ask_size > 0):
            self.invalid_quotes += 1
            return
        if symbol in self.last:
            self.max_gap_ms[symbol] = max(self.max_gap_ms[symbol], (now-self.last[symbol])*1000)
        self.last[symbol] = now
        self.counts[symbol] += 1

    def sample(self, now, wall):
        self.clock_ok &= abs((wall-self.wall) - (now-self.started)) <= 0.25
        ages = {s: (now-self.last[s])*1000 if s in self.last else None for s in SYMBOLS}
        stale = any(age is None or age > 1000 for age in ages.values())
        if now-self.started >= 60:
            self.stale_samples += int(stale)
            self.recoveries += int(self.was_stale and not stale)
            self.was_stale = stale
        return dict(counts=self.counts.copy(), quote_age_ms=ages,
                    stale_samples_after_warmup=self.stale_samples,
                    observed_freshness_recoveries=self.recoveries,
                    max_interquote_gap_ms=self.max_gap_ms.copy(),
                    clock_ok=self.clock_ok, invalid_quotes=self.invalid_quotes)


def config():
    from nautilus_trader.adapters.binance.config import BinanceDataClientConfig
    from nautilus_trader.config import InstrumentProviderConfig, TradingNodeConfig, LoggingConfig
    from nautilus_trader.model.identifiers import InstrumentId
    return TradingNodeConfig(
        logging=LoggingConfig(log_level='WARNING'),
        data_clients={'BINANCE': BinanceDataClientConfig(
            api_key=None, api_secret=None,
            instrument_provider=InstrumentProviderConfig(
                load_ids=frozenset(InstrumentId.from_str(s+'.BINANCE') for s in SYMBOLS)),
            update_instruments_interval_mins=None)},
        exec_clients={}, timeout_connection=30.0, timeout_disconnection=5.0,
        timeout_post_stop=1.0, timeout_shutdown=5.0)


def write_json(path, report):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(report, indent=2)+'\n')
    temp.replace(path)


async def observe(node, health, seconds, root, observer=None, recovery_drill=False):
    from .recovery import SubscriptionDrill, assessment
    drill = SubscriptionDrill() if recovery_drill else None
    task = asyncio.create_task(node.run_async())
    premature = False
    shutdown_ok = False
    try:
        while time.monotonic()-health.started < seconds:
            snapshot = health.sample(time.monotonic(), time.time())
            if drill is not None:
                drill.step(time.monotonic()-health.started, snapshot, observer)
            write_json(root/'health.json', dict(running=True, **snapshot))
            elapsed = int(time.monotonic()-health.started)
            if elapsed % 10 == 0:
                print(f'[nautilus-observe] elapsed={elapsed}/{seconds}s counts={snapshot["counts"]}', flush=True)
            if task.done():
                task.result()
                premature = True
                break
            await asyncio.sleep(1)
        final = health.sample(time.monotonic(), time.time())
        elapsed = time.monotonic()-health.started
    finally:
        try:
            await asyncio.wait_for(node.stop_async(), timeout=15)
            shutdown_ok = True
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    no_orders = len(node.cache.orders()) == 0
    checks = dict(duration_completed=elapsed >= seconds and not premature,
                  both_symbols_received=all(final['counts'].values()),
                  no_stale_samples=final['stale_samples_after_warmup'] == 0,
                  final_quotes_fresh=all(a is not None and a <= 1000 for a in final['quote_age_ms'].values()),
                  clock_stable=final['clock_ok'], valid_quotes=final['invalid_quotes'] == 0,
                  stopped_cleanly=shutdown_ok, no_orders=no_orders)
    write_json(root/'health.json', dict(running=False, **final))
    observation_checks = checks.copy()
    drill_report = drill.report(elapsed) if drill is not None else None
    if drill_report is not None:
        checks = assessment(observation_checks, drill_report)
    prefix = 'subscription_recovery' if recovery_drill else 'observation_checks'
    return dict(approved=False, real_orders=False, observe_only=True,
                status=prefix+('_passed' if all(checks.values()) else '_failed'),
                ordinary_observation_checks=observation_checks, recovery_drill=drill_report,
                checks=checks, elapsed_seconds=elapsed, health=final,
                nautilus_version=version('nautilus_trader'),
                limitations=['No execution clients, account access or orders.',
                             'Receipt freshness sampled once per second after 60s startup allowance.',
                             'Freshness recovery is not proof of socket reconnect or gap backfill.',
                             'Adapter errors are in adapter.log; this report does not classify every upstream error.',
                             'A finite run does not certify 24/7 operation, latency or profitability.'])


def worker(seconds, root, recovery_drill=False):
    if version('nautilus_trader') != '1.231.0':
        raise ValueError('Expected NautilusTrader 1.231.0')
    from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
    from nautilus_trader.common.actor import Actor
    from nautilus_trader.live.node import TradingNode
    from nautilus_trader.model.identifiers import InstrumentId
    health = Health(time.monotonic(), time.time())

    class QuoteObserver(Actor):
        def on_start(self):
            self.resume_quotes()

        def resume_quotes(self):
            for symbol in SYMBOLS:
                self.subscribe_quote_ticks(InstrumentId.from_str(symbol+'.BINANCE'))

        def pause_quotes(self):
            for symbol in SYMBOLS:
                self.unsubscribe_quote_ticks(InstrumentId.from_str(symbol+'.BINANCE'))

        def on_quote_tick(self, quote):
            health.quote(quote.instrument_id.symbol.value, time.monotonic(),
                         quote.bid_price.as_decimal(), quote.ask_price.as_decimal(),
                         quote.bid_size.as_decimal(), quote.ask_size.as_decimal())

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    node = TradingNode(config=config(), loop=loop)
    try:
        observer = QuoteObserver()
        node.trader.add_actor(observer)
        node.add_data_client_factory('BINANCE', BinanceLiveDataClientFactory)
        node.build()
        report = loop.run_until_complete(observe(node, health, seconds, root, observer, recovery_drill))
    finally:
        node.dispose()
        if not loop.is_closed():
            loop.close()
    write_json(root/'observation.json', report)
    return 0 if all(report['checks'].values()) else 2


def supervise(seconds, root, recovery_drill=False):
    root.mkdir(parents=True, exist_ok=False)
    status = dict(approved=False, real_orders=False, status='running', seconds=seconds, recovery_drill=recovery_drill)
    write_json(root/'run.json', status)
    process = None
    try:
        with (root/'adapter.log').open('w') as log:
            process = subprocess.Popen([sys.executable, '-u', '-m', 'integrations.nautilus.observe', '--worker',
                                        '--seconds', str(seconds), '--output-dir', str(root)] +
                                       (['--recovery-drill'] if recovery_drill else []),
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                deadline = time.monotonic()+seconds+60
                while True:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(process.args, seconds+60)
                    try:
                        code = process.wait(timeout=min(10, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        if (root/'adapter.log').stat().st_size > 64*1024*1024:
                            raise ValueError('Adapter log exceeded 64 MiB budget')
                        health_path = root/'health.json'
                        detail = json.loads(health_path.read_text()) if health_path.exists() else {}
                        print(f'[nautilus-observe] waiting; counts={detail.get("counts", {})}', flush=True)
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
        path = root/'observation.json'
        if code == 0 and path.is_file():
            report = json.loads(path.read_text())
            expected_status = 'subscription_recovery_passed' if recovery_drill else 'observation_checks_passed'
            if report.get('status') != expected_status or not report.get('checks') or not all(report['checks'].values()):
                raise ValueError('Worker success without passing report')
            status['status'] = 'complete'
        else:
            status['status'] = 'failed'
        status['worker_returncode'] = code
    except BaseException as error:
        status.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                      error_type=type(error).__name__)
        raise
    finally:
        write_json(root/'run.json', status)
    if (root/'observation.json').is_file():
        print((root/'observation.json').read_text())
    print(f'Run status: {status["status"]}; logs: {root / "adapter.log"}')
    return 0 if status['status'] == 'complete' else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=300)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--recovery-drill', action='store_true',
                        help='Fixed 10-second subscription pause at 90s; no transport outage')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 120 <= args.seconds <= 21600:
        parser.error('Duration must be 120–21600 seconds')
    if args.recovery_drill and args.seconds < 180:
        parser.error('Recovery drill requires at least 180 seconds')
    if args.worker:
        return worker(args.seconds, args.output_dir.resolve(), args.recovery_drill)
    return supervise(args.seconds, args.output_dir.resolve(), args.recovery_drill)


if __name__ == '__main__':
    raise SystemExit(main())
