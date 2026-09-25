import math
import json
import tempfile
import unittest
from pathlib import Path

from diagnose_pack_costs import barrier, diagnose, run
from engine_v1.dataset import sha256
import test_pack_summary


class PackCostTests(unittest.TestCase):
    def test_saved_report_provenance_and_no_overwrite(self):
        pack, reports = test_pack_summary.PackSummaryTests().fixture()
        pack.update(symbol='ETHUSDT', cost_barrier_log_bps=barrier(10, 2))
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            p = root / 'pack.json'
            p.write_text(json.dumps(pack))
            paths = []
            for i, report in enumerate(reports):
                report['pack_sha256'] = sha256(p)
                path = root / f'{i}.json'
                path.write_text(json.dumps(report))
                paths.append(path)
            output = root / 'costs.json'
            result = run(p, paths, output, 10, 2)
            self.assertEqual(result['common_rows'], 400)
            saved = json.loads(output.read_text())
            self.assertFalse(saved['approved'])
            self.assertIsNone(saved['pnl'])
            self.assertEqual(len(saved['sources']), 3)
            with self.assertRaises(ValueError):
                run(p, paths, output, 10, 2)
            with self.assertRaises(ValueError):
                run(p, [paths[0], paths[0]], root / 'duplicate.json', 10, 2)

    def test_break_even_identity(self):
        for fee, slip in ((0, 0), (10, 2), (7.5, 2)):
            ratio = math.exp(barrier(fee, slip) / 10000)
            net_factor = ratio * (1-slip/10000) * (1-fee/10000)
            net_factor /= (1+slip/10000) * (1+fee/10000)
            self.assertAlmostEqual(net_factor, 1)
        self.assertAlmostEqual(barrier(10, 2), 24.000006720004002)

    def test_invalid_costs(self):
        for bad in (-1, 10000, math.inf, math.nan):
            with self.assertRaises(ValueError):
                barrier(bad, 2)
            with self.assertRaises(ValueError):
                barrier(10, bad)

    def test_shortfall_and_empty_selection_preserve_original_eligibility(self):
        s = {'captures': 2, 'common_rows': 100, 'models': {
            'baseline': {'selected_samples': 10, 'selected_weighted_mean_quote_log_bps': .45,
                         'cost_eligible_forecasts': 0},
            'empty': {'selected_samples': 0, 'selected_weighted_mean_quote_log_bps': None,
                      'cost_eligible_forecasts': 0}}}
        result = diagnose(s, 10, 2)['models']
        self.assertAlmostEqual(result['baseline']['selected_mean_minus_cost_log_bps'], -23.55000672)
        self.assertIsNone(result['empty']['selected_mean_minus_cost_log_bps'])
        self.assertEqual(diagnose(s, 0, 0)['models']['baseline']['frozen_cost_eligible_forecasts'], 0)
