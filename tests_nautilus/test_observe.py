import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from integrations.nautilus.observe import Health, config, supervise


class ObserveTests(unittest.TestCase):
    def test_stale_feed_recovery_does_not_erase_failure(self):
        health = Health(0, 1000)
        for symbol in ('BTCUSDT', 'ETHUSDT'):
            health.quote(symbol, 60, 100, 101, 1, 1)
        self.assertEqual(health.sample(60.5, 1060.5)['stale_samples_after_warmup'], 0)
        self.assertEqual(health.sample(62, 1062)['stale_samples_after_warmup'], 1)
        for symbol in ('BTCUSDT', 'ETHUSDT'):
            health.quote(symbol, 63, 100, 101, 1, 1)
        report = health.sample(63.1, 1063.1)
        self.assertEqual(report['stale_samples_after_warmup'], 1)
        self.assertEqual(report['observed_freshness_recoveries'], 1)
        self.assertEqual(report['max_interquote_gap_ms']['BTCUSDT'], 3000)

    def test_missing_symbol_clock_jump_and_bad_quote(self):
        health = Health(0, 1000)
        health.quote('BTCUSDT', 60, 101, 100, 1, 1)
        report = health.sample(61, 1062)
        self.assertFalse(report['clock_ok'])
        self.assertEqual(report['invalid_quotes'], 1)
        self.assertEqual(report['stale_samples_after_warmup'], 1)
        self.assertEqual(report['counts']['BTCUSDT'], 0)
        self.assertFalse(health.sample(62, 1062)['clock_ok'])

    def test_data_only_configuration_and_real_node_build(self):
        from nautilus_trader.live.node import TradingNode
        from nautilus_trader.adapters.binance.factories import BinanceLiveDataClientFactory
        cfg = config()
        self.assertEqual(cfg.exec_clients, {})
        self.assertIsNone(cfg.data_clients['BINANCE'].api_key)
        self.assertIsNone(cfg.data_clients['BINANCE'].api_secret)
        self.assertEqual(len(cfg.data_clients['BINANCE'].instrument_provider.load_ids), 2)
        loop = asyncio.new_event_loop()
        node = TradingNode(config=cfg, loop=loop)
        try:
            node.add_data_client_factory('BINANCE', BinanceLiveDataClientFactory)
            node.build()
            self.assertEqual(len(node.cache.orders()), 0)
        finally:
            node.dispose()

    def test_existing_run_refused_before_worker_launch(self):
        with tempfile.TemporaryDirectory() as tmp, patch('subprocess.Popen') as launch:
            with self.assertRaises(FileExistsError):
                supervise(120, Path(tmp))
            launch.assert_not_called()

    def test_hung_worker_is_terminated_and_marked_failed(self):
        import json
        import subprocess
        with tempfile.TemporaryDirectory() as tmp, patch('subprocess.Popen') as launch, \
             patch('integrations.nautilus.observe.time.monotonic', side_effect=[0, 1000]), \
             patch('integrations.nautilus.observe.os.killpg') as kill:
            launch.return_value.pid = 1234
            root = Path(tmp)/'run'
            with self.assertRaises(subprocess.TimeoutExpired):
                supervise(120, root)
            kill.assert_called_once()
            self.assertEqual(json.loads((root/'run.json').read_text())['status'], 'failed')

    def test_zero_exit_without_report_is_failed(self):
        import json
        with tempfile.TemporaryDirectory() as tmp, patch('subprocess.Popen') as launch:
            launch.return_value.wait.return_value = 0
            root = Path(tmp)/'run'
            self.assertEqual(supervise(120, root), 2)
            self.assertEqual(json.loads((root/'run.json').read_text())['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
