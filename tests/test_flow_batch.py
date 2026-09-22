import unittest
from research_tradeflow_batch import schedule, summarize


class FlowBatchTests(unittest.TestCase):
    def test_schedule_excludes_reserved_month(self):
        folds=schedule('2026-05-01',4,'2026-09-01')
        self.assertEqual(folds[0]['train_start'],'2026-03-01')
        self.assertEqual(folds[-1]['test_start'],'2026-08-01')
        self.assertEqual(folds[-1]['test_end'],'2026-09-01')
        for first,months in [('2026-05-01',5),('2026-05-02',4),('2026-05-01',0)]:
            with self.assertRaises(ValueError):schedule(first,months,'2026-09-01')

    def test_summary_does_not_confuse_relative_improvement_with_zero_baseline(self):
        report={'summary':{'test_rmse_log_bps':{'candles_only':3,'candles_plus_flow':2},'zero_rmse_log_bps':1}}
        s=summarize([({'test_start':'2026-05-01'},report)])
        self.assertEqual(s['flow_lower_rmse_than_candles_folds'],1)
        self.assertEqual(s['flow_lower_rmse_than_zero_folds'],0)
        self.assertEqual(s['candles_lower_rmse_than_zero_folds'],0)

    def test_failed_download_stops_before_audit_or_evaluation(self):
        import argparse
        import subprocess
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from research_tradeflow_batch import run
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for month in ('03','04','05'):
                path=root/f'binance-ETHUSDT-2026-{month}.csv'
                path.write_text('fixture');path.with_suffix('.json').write_text('{}')
            a=argparse.Namespace(first_test='2026-05-01',months=1,reserve_from='2026-09-01',
                output_dir=root/'out',root=root/'downloads',candle_root=root,symbol='ETHUSDT')
            with patch('research_tradeflow_batch.subprocess.run',side_effect=subprocess.CalledProcessError(2,'download')) as call,patch('sys.stdout'):
                with self.assertRaises(subprocess.CalledProcessError):run(a)
            self.assertEqual(call.call_count,1)
            self.assertFalse((a.output_dir/'summary.json').exists())
            self.assertTrue((a.output_dir/'protocol.json').exists())
