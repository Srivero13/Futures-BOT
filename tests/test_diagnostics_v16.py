import unittest
import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from diagnose_v16 import main
from engine_v1.dataset import sha256
from dataclasses import replace
import numpy as np
from diagnose_v16 import diagnose, Distribution
from backtest_v16 import Costs
from engine_v1.model import RidgeModel
from engine_v1.nonlinear import PolynomialModel


def model(pred=1,buffer=2):
    return RidgeModel('ETHUSDT',3,[0]*6,[1]*6,[0]*6,pred,buffer,0,60000,100,30,1,1)


def factory():
    return iter([np.array([[60000,240000,0,0,0,.001,0,0,5],
                          [120000,300000,0,0,0,.002,0,0,-5]],dtype=float)])


class DiagnosticTests(unittest.TestCase):
    def test_weak_raw_forecasts(self):
        r=diagnose(factory,model(),60000,360000)
        self.assertEqual(r['diagnosis'],'raw_forecasts_never_clear_threshold')
        self.assertEqual(r['distributions']['prediction_log_bps']['mean'],1)
        self.assertEqual(r['distributions']['lower_bound_log_bps']['max'],-1)
        self.assertEqual(r['accepted'],2)
        self.assertFalse(r['approved'])
        self.assertIsNone(r['pnl'])

    def test_buffer_blocks_raw_candidates(self):
        r=diagnose(factory,model(40,20),60000,360000)
        self.assertEqual(r['raw_forecast_above_threshold'],2)
        self.assertEqual(r['blocked_by_calibration_buffer'],2)
        self.assertEqual(r['calibrated_forecast_above_threshold'],0)
        self.assertEqual(r['diagnosis'],'calibration_buffer_blocks_all_raw_candidates')

    def test_candidates_and_threshold_agreement(self):
        r=diagnose(factory,model(40,1),60000,360000)
        self.assertEqual(r['calibrated_forecast_above_threshold'],2)
        self.assertAlmostEqual(r['entry_threshold_log_bps'],28.000006846671294)
        self.assertLess(r['distributions']['threshold_shortfall_log_bps']['max'],0)

    def test_all_ood(self):
        m=model(); m.mean=[100]*6
        r=diagnose(factory,m,60000,360000)
        self.assertEqual(r['diagnosis'],'all_examples_rejected')
        self.assertIsNone(r['rmse_log_bps'])
        self.assertIsNone(r['distributions']['prediction_log_bps']['mean'])

    def test_scaled_buffer(self):
        m=replace(model(1,2),volatility_scaled=True)
        r=diagnose(factory,m,60000,360000)
        self.assertAlmostEqual(r['distributions']['buffer_log_bps']['mean'],30*np.sqrt(3))

    def test_polynomial(self):
        m=PolynomialModel('ETHUSDT',3,[0]*27,[1]*27,[0]*27,40,1,0,60000,100,30,1,1)
        r=diagnose(factory,m,60000,360000)
        self.assertEqual(r['calibrated_forecast_above_threshold'],2)

    def test_end_exclusive_and_invalid_boundaries(self):
        r=diagnose(factory,model(),60000,300000)
        self.assertEqual(r['examples'],1)
        with self.assertRaises(ValueError):
            diagnose(factory,model(),0,360000)
        with self.assertRaises(ValueError):
            diagnose(factory,model(),60000,120000)
        with self.assertRaises(ValueError):
            diagnose(factory,model(),60000,360000,Costs(fee_bps=-1))

    def test_bounded_quantiles_exact_extrema(self):
        d=Distribution(); d.add(np.arange(110000,dtype=float))
        r=d.report()
        self.assertTrue(r['quantiles_approximate'])
        self.assertEqual(r['quantile_sample_size'],100000)
        self.assertEqual(r['max'],109999)
        self.assertEqual(r['mean'],54999.5)

    def test_cli_integrity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            path=root/'data.csv'
            with path.open('w') as f:
                writer=csv.DictWriter(f,fieldnames=['timestamp','open','high','low','close','volume'])
                writer.writeheader()
                for i in range(1440):
                    writer.writerow(dict(timestamp=i*60,open=100,high=100,low=100,close=100,volume=1))
            meta=dict(sha256=sha256(path),venue='binance',symbol='ETHUSDT',timeframe_ms=60000)
            path.with_suffix('.json').write_text(json.dumps(meta))
            artifact=root/'model.json'
            replace(model(),calibration_end_ms=0).save(artifact)
            output=root/'diagnostic.json'
            args=['diagnose_v16.py','--files',str(path),'--model',str(artifact),
                  '--start','1970-01-01','--end','1970-01-02','--output',str(output)]
            with patch('sys.argv',args),patch('sys.stdout'),patch('sys.stderr'):
                self.assertEqual(main(),0)
                saved=output.read_bytes()
                self.assertEqual(main(),2)
                self.assertEqual(output.read_bytes(),saved)
                self.assertEqual(json.loads(saved)['diagnosis'],'raw_forecasts_never_clear_threshold')
                output.unlink()
                meta['symbol']='BTCUSDT'
                path.with_suffix('.json').write_text(json.dumps(meta))
                self.assertEqual(main(),2)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
