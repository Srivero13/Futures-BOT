import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from walkforward_v16 import ranking
from diagnose_saved_research import diagnostic,run


class SavedDiagnosticTests(unittest.TestCase):
    def test_moments_equal_raw_errors_and_empty_buckets(self):
        rng=np.random.default_rng(44)
        cal=np.column_stack((np.linspace(-100,100,100),np.zeros(100)))
        p=rng.normal(size=80)+2;y=rng.normal(size=80)
        r=ranking(cal,np.column_stack((p,y)))
        d=diagnostic(r,80)
        self.assertAlmostEqual(d['mean_error_log_bps'],np.mean(p-y))
        self.assertAlmostEqual(d['centered_error_rmse_log_bps'],np.std(p-y))
        self.assertAlmostEqual(d['actual_return_std_log_bps'],np.std(y))
        self.assertEqual(d['top_bucket']['count'],0)
        with self.assertRaises(ValueError):diagnostic(r,81)

    def test_pooling_counts_duplicates_and_output_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);paths=[]
            for i,n in enumerate((40,80)):
                y=np.ones(n);pred=np.ones(n)*(i+2)
                pairs=np.column_stack((pred,y));r=ranking(pairs,pairs)
                report={'protocol':{'symbol':'ETHUSDT','backend':'ridge',
                        'calibration_end_ms':1780272000000+i*2678400000,'test_end_ms':1782864000000+i*2678400000},
                        'summary':{'paired_rows':{'test':n}},'rankings':{'candles_only':r}}
                p=root/f'{i}.json';p.write_text(json.dumps(report));paths.append(p)
            output=root/'out.json';s=run(paths,output)['summary'][0]
            self.assertAlmostEqual(s['pooled_rmse_log_bps'],np.sqrt(3))
            with self.assertRaises(ValueError):run(paths,output)
            with self.assertRaises(ValueError):run([paths[0],paths[0]],root/'other.json')
