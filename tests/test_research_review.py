import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from engine_v1.dataset import sha256
from review_research import cross_review, run
import test_hourly_robustness
import test_pack_summary


def cross_fixture():
    return {'approved': False, 'pnl': None,
        'protocol': {'hypothesis': 'Past BTC returns add predictive value to ETH-only features'},
        'summary': {'paired_test_samples': 2}, 'folds': [{
            'decision_ms': [0, 3600000], 'label_end_ms': [3660000, 7260000],
            'actual_reference_return_log_bps': [1, -1],
            'predictions': {'eth_only': [0, 0], 'eth_plus_btc': [.5, -.5]},
            'summary': {'models': {'eth_only': {'rmse_log_bps': 1},
                                    'eth_plus_btc': {'rmse_log_bps': .5}}}}]}


class ResearchReviewTests(unittest.TestCase):
    def test_recomputed_paired_metrics(self):
        result = cross_review(cross_fixture())
        self.assertEqual(result['paired_test_samples'], 2)
        self.assertEqual(result['btc_beats_eth_rmse_folds'], 1)
        self.assertEqual(result['recomputed_pooled_rmse_log_bps'],
                         {'zero': 1., 'eth_only': 1., 'eth_plus_btc': .5})

    def test_bad_predictions_and_repeated_intervals_rejected(self):
        for value in ([0], [math.nan, 0], [100, 100]):
            report = cross_fixture()
            report['folds'][0]['predictions']['eth_only'] = value
            with self.assertRaises(ValueError):
                cross_review(report)
        report = cross_fixture()
        report['folds'].append(copy.deepcopy(report['folds'][0]))
        with self.assertRaises(ValueError):
            cross_review(report)

    def test_end_to_end_sources_and_output_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def save(name, data):
                path = root/name
                path.write_text(json.dumps(data))
                return path
            pack, reports = test_pack_summary.PackSummaryTests().fixture()
            p = save('pack.json', pack)
            paths = []
            for index, report in enumerate(reports):
                report['pack_sha256'] = sha256(p)
                paths.append(save(f'pack-{index}.json', report))
            hourly = save('hourly.json', test_hourly_robustness.fixture())
            cross = save('cross.json', cross_fixture())
            output = root/'review.json'
            result = run(p, paths, hourly, cross, output, 10, 2)
            self.assertFalse(result['approved'])
            self.assertEqual(len(result['sources']), 5)
            self.assertEqual(json.loads(output.read_text())['status'], 'research_only_no_promotion_decision')
            with self.assertRaises(ValueError):
                run(p, paths, hourly, cross, output, 10, 2)
