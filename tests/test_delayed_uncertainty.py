import unittest
import numpy as np
from diagnose_delayed_uncertainty import summarize


class UncertaintyTests(unittest.TestCase):
    def test_paired_identical_predictions_and_constant_selected_return(self):
        y=np.ones(600);p=np.ones(600)*.5;t=np.arange(600,dtype=np.int64)*6_000_000_000
        result=summarize(y,p,p,np.ones(600,dtype=bool),t)
        self.assertEqual(result['metrics']['model_minus_imbalance_rmse_log_bps']['percentile_95_interval'],[0,0])
        self.assertEqual(result['metrics']['frozen_top_bucket_mean_quote_log_bps']['percentile_95_interval'],[1,1])
        self.assertEqual(result['metrics']['model_minus_zero_rmse_log_bps']['estimate'],-.5)
        self.assertEqual(result,summarize(y,p,p,np.ones(600,dtype=bool),t))

    def test_empty_selection_and_short_history(self):
        y=np.ones(200);t=np.arange(200,dtype=np.int64)*6_000_000_000
        r=summarize(y,y,y,np.zeros(200,dtype=bool),t)
        self.assertIsNone(r['metrics']['frozen_top_bucket_mean_quote_log_bps']['percentile_95_interval'])
        with self.assertRaises(ValueError):summarize(y,y,y,y,np.zeros(200))

    def test_saved_model_and_provenance_gate(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from test_delayed_training import DelayedTrainingTests
        from train_delayed_microstructure import fit
        from diagnose_delayed_uncertainty import run
        from engine_v1.dataset import sha256
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);train=root/'train';test=root/'test'
            fixture=DelayedTrainingTests()
            fixture.dataset(train,10**15,'capture-a');fixture.dataset(test,2*10**15,'capture-b')
            model=root/'model.json'
            with patch('train_delayed_microstructure.time.time_ns',return_value=15*10**14):fit(train,model)
            before=sha256(model)
            result=run(train,test,model,root/'diagnostic.json')
            self.assertEqual(result['samples'],200)
            self.assertEqual(before,sha256(model))
            with self.assertRaises(ValueError):run(test,test,model,root/'bad.json')
            self.assertFalse((root/'bad.json').exists())
