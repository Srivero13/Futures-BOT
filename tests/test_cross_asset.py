import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import research_cross_asset as research
from engine_v1.dataset import sha256
from train_v15 import timestamp


def rows(n=300):
    return [dict(timestamp=i*60000, open=str(100+i*.01),
                 close=str(100+i*.01), high=str(100+i*.01),
                 low=str(100+i*.01), volume='1') for i in range(n)]


class CrossAssetTests(unittest.TestCase):
    def test_feature_causality_and_delayed_target(self):
        eth, btc = rows(), rows()
        original, _ = research.paired_examples(eth, btc, 1000*60000)
        first = original[0]
        self.assertEqual(first[0], 60*60000)
        self.assertEqual(first[1], 121*60000)
        self.assertAlmostEqual(first[-1], np.log(float(eth[121]['open'])/float(eth[61]['open']))*10000)
        for r in btc[60:]:
            r.update(open='1000', close='1000', high='1000', low='1000')
        changed, _ = research.paired_examples(eth, btc, 1000*60000)
        np.testing.assert_array_equal(first, changed[0])
        eth[61]['open'] = '90'
        changed, _ = research.paired_examples(eth, btc, 1000*60000)
        np.testing.assert_array_equal(first[:-1], changed[0, :-1])
        self.assertNotEqual(first[-1], changed[0, -1])

    def test_coverage_reserve_and_gaps(self):
        with self.assertRaises(ValueError):
            research.paired_examples(rows(), rows()[1:], 1000*60000)
        with self.assertRaisesRegex(ValueError, 'reserved'):
            research.paired_examples(rows(), rows(), 200*60000)
        data = rows()
        del data[130:140]
        paired, counts = research.paired_examples(data, data, 1000*60000)
        self.assertEqual(counts['gaps'], 1)
        self.assertFalse(any(start < 140*60000 and end >= 130*60000 for start, end in paired[:, :2]))

    def test_partition_purges_boundary_labels(self):
        data = np.array([[0, 61, 1], [60, 121, 2], [120, 181, 3]])
        np.testing.assert_array_equal(research.split(data, 0, 121), data[:1])

    def test_fit_and_cutoffs_do_not_use_test_outcomes(self):
        rng = np.random.default_rng(11)
        def block(n):
            x = rng.normal(size=(n, 10))
            y = 2*x[:, 6]+rng.normal(scale=.1, size=n)
            return np.column_stack((np.arange(n), np.arange(n)+1, x, y))
        train, cal, test = block(1200), block(200), block(200)
        result = research.compare_fold(train, cal, test)
        changed = test.copy()
        changed[:, -1] += 100
        altered = research.compare_fold(train, cal, changed)
        self.assertEqual(result['weights'], altered['weights'])
        self.assertEqual(result['predictions'], altered['predictions'])
        for name in result['weights']:
            self.assertEqual(result['summary']['models'][name]['calibration_downside_buffer_log_bps'],
                             altered['summary']['models'][name]['calibration_downside_buffer_log_bps'])
        self.assertLess(result['summary']['btc_minus_eth_rmse_log_bps'], -1)

    def test_protocol_and_saved_forecasts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = []
            for symbol in ('ETHUSDT', 'BTCUSDT'):
                p = root/f'{symbol}.csv'
                p.write_text('fixture')
                p.with_suffix('.json').write_text(json.dumps(dict(sha256=sha256(p), venue='binance',
                    symbol=symbol, timeframe_ms=60000, last_open_ms=1000)))
                files.append(p)
            rng = np.random.default_rng(42)
            stamps = np.arange(timestamp('2025-11-01'), timestamp('2026-04-01'), 3600000)
            matrix = np.column_stack((stamps, stamps+61*60000, rng.normal(size=(len(stamps), 11))))
            output = root/'report.json'
            with patch.object(research, 'paired_examples', return_value=(matrix, {})), patch('sys.stdout'):
                summary = research.run([files[0]], [files[1]], '2026-03-01', 1, '2026-09-01', output)
            saved = json.loads(output.read_text())
            self.assertFalse(saved['approved'])
            self.assertIsNone(saved['pnl'])
            self.assertEqual(summary['folds'], 1)
            fold = saved['folds'][0]
            self.assertEqual(len(fold['predictions']['eth_only']), len(fold['predictions']['eth_plus_btc']))
            self.assertTrue(output.with_suffix('.protocol.json').exists())
            with self.assertRaises(ValueError):
                research.run([files[0]], [files[1]], '2026-03-01', 1, '2026-09-01', output)

    def test_reserved_schedule_before_reading(self):
        with patch.object(research, 'verify') as verify:
            with self.assertRaisesRegex(ValueError, 'reserved'):
                research.run([], [], '2026-08-01', 2, '2026-09-01', Path('unused.json'))
            verify.assert_not_called()
