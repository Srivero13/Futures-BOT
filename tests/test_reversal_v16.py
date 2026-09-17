import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from reversal_v16 import decline_score,threshold_from_scores,calibrate,evaluate,run
from backtest_v16 import simulate
from engine_v1.model import RidgeModel


def rows(n=180):
    return [dict(timestamp=i*60000,open='100',close='100',high='100',low='100',volume='1') for i in range(n)]


class ReversalTests(unittest.TestCase):
    def test_score_sign_scale_and_floor(self):
        x=np.array([0,0,-.02,.01,0,0])
        self.assertAlmostEqual(decline_score(x),.02/(.01*np.sqrt(20)))
        x[2]=.02
        self.assertLess(decline_score(x),0)
        x[3]=0
        self.assertTrue(np.isfinite(decline_score(x)))
        with self.assertRaises(ValueError):decline_score([0,0,0,-1,0,0])

    def test_fixed_percentile_and_minimum(self):
        self.assertAlmostEqual(threshold_from_scores(np.arange(100)),98.01)
        self.assertEqual(threshold_from_scores(-np.arange(100)),0)
        with self.assertRaises(ValueError):threshold_from_scores([1]*99)

    def test_calibration_excludes_future_prices(self):
        data=rows(1600)
        start=30*60000;end=1530*60000
        first=calibrate(data,start,end)
        data[-1].update(close='50',low='50')
        second=calibrate(data,start,end)
        self.assertEqual(first,second)
        self.assertEqual(first['grid_examples'],100)
        self.assertEqual(first['threshold'],0)
        with self.assertRaises(ValueError):calibrate(data[25:],start,end)

    def test_fixed_rule_delay_costs_and_no_overlapping_positions(self):
        data=rows()
        data[29].update(close='90',low='90')
        result=evaluate(data,30*60000,180*60000,{'threshold':0,'end_ms':30*60000})
        self.assertGreater(result['summary']['closed_trades'],0)
        self.assertFalse(result['approved'])
        self.assertNotIn('cost_gate_candidates',result['summary'])
        for trade in result['trades']:
            self.assertEqual(trade['decision_ms']%(15*60000),0)
            self.assertEqual(trade['entry_ms']-trade['decision_ms'],60000)
            self.assertEqual(trade['exit_ms']-trade['entry_ms'],15*60000)
            self.assertGreater(float(trade['fees']),0)
        for a,b in zip(result['trades'],result['trades'][1:]):
            self.assertGreaterEqual(b['entry_ms'],a['exit_ms'])
        self.assertLess(float(result['summary']['net_pnl']),0)

    def test_no_signal_and_calibration_overlap(self):
        result=evaluate(rows(),30*60000,180*60000,{'threshold':0,'end_ms':30*60000})
        self.assertEqual(result['summary']['closed_trades'],0)
        with self.assertRaises(ValueError):evaluate(rows(),30*60000,180*60000,{'threshold':0,'end_ms':31*60000})

    def test_callback_contract_and_original_model_path(self):
        m=RidgeModel('ETHUSDT',15,[0]*6,[1]*6,[0]*6,0,0,0,0,100,30,1,1)
        report=simulate(rows(),m,30*60000,180*60000)
        self.assertEqual(report['summary']['closed_trades'],0)
        with self.assertRaises(ValueError):
            simulate(rows(),m,30*60000,180*60000,entry_rule=lambda x,ts:None)

    def test_reserved_date_rejected_before_reading(self):
        with tempfile.TemporaryDirectory() as root:
            with patch('reversal_v16.candles') as read:
                with self.assertRaisesRegex(ValueError,'reserved'):
                    run([],'ETHUSDT','2026-08-01',2,'2026-09-01',Path(root)/'out.json')
                read.assert_not_called()

    def test_orchestration_publishes_protocol_and_summary(self):
        # Numerical execution is exercised above; stub expensive monthly IO here.
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);p=root/'data.csv';p.write_text('fixture')
            from engine_v1.dataset import sha256
            p.with_suffix('.json').write_text(json.dumps(dict(last_open_ms=1000,sha256=sha256(p),venue='binance',symbol='ETHUSDT',timeframe_ms=60000)))
            cal={'threshold':1,'grid_examples':100,'end_ms':0}
            result=evaluate(rows(),30*60000,180*60000,cal)
            with patch('reversal_v16.calibrate',return_value=cal),patch('reversal_v16.evaluate',return_value=result),patch('sys.stdout'):
                report=run([p],'ETHUSDT','2026-03-01',1,'2026-09-01',root/'result.json')
            self.assertFalse(report['approved'])
            self.assertEqual(report['summary']['closed_trades'],0)
            self.assertTrue((root/'result.protocol.json').exists())
            self.assertEqual(json.loads((root/'result.json').read_text())['protocol']['horizon_minutes'],15)


if __name__=='__main__':unittest.main()
