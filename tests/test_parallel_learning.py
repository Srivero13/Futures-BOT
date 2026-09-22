import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np
from engine_v1.dataset import examples
from evaluate_tradeflow import flow_features, fit_predict
from engine_v1.research_mlp import polynomial_predict


class LearningControls(unittest.TestCase):
    def test_raw_flow_candles_labels_recover_known_signal(self):
        rng=np.random.default_rng(21);n=4000
        imbalance=rng.uniform(-.8,.8,n)
        # At decision i+1, closed flow through i predicts the open i+2 / open i+1 return.
        prices=np.ones(n)*100
        for j in range(2,n):
            signal=imbalance[max(0,j-6):j-1].mean()
            prices[j]=prices[j-1]*np.exp(signal*.001)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);c=root/'c.csv';f=root/'f.csv'
            with c.open('w') as h:
                w=csv.writer(h);w.writerow(['timestamp','open','high','low','close','volume'])
                for i,p in enumerate(prices):w.writerow([i*60,p,p,p,p,1])
            with f.open('w') as h:
                w=csv.writer(h);w.writerow(['timestamp','available_at_ms','taker_buy_quote','taker_sell_quote','agg_events'])
                for i,z in enumerate(imbalance):w.writerow([i*60,(i+1)*60000,1+z,1-z,10])
            flow=flow_features([f]);rows=np.concatenate(list(examples([c],horizon=1)))
            x=np.array([flow[int(r[0])] for r in rows]);y=rows[:,8]
            np.testing.assert_allclose(y,10*x[:,0],atol=1e-8)
            pred=fit_predict(x[:2500],y[:2500],[x[2500:]])[0]
            self.assertLess(np.mean((pred-y[2500:])**2),np.mean(y[2500:]**2)*.01)
            shuffled=y[:2500].copy();rng.shuffle(shuffled)
            bad=fit_predict(x[:2500],shuffled,[x[2500:]])[0]
            self.assertGreater(np.mean((bad-y[2500:])**2),np.mean(y[2500:]**2)*.8)

    def test_polynomial_recovers_nonlinear_signal(self):
        rng=np.random.default_rng(4);x=rng.normal(size=(2000,3));y=x[:,0]*x[:,1]*5
        p=polynomial_predict(x[:1500],y[:1500],[x[1500:]])[0]
        self.assertLess(np.mean((p-y[1500:])**2),np.mean(y[1500:]**2)*.01)

    @unittest.skipUnless(importlib.util.find_spec('torch'),'Optional PyTorch not installed')
    def test_mlp_recovers_signal_on_cpu(self):
        from engine_v1.research_mlp import fit_predict as mlp
        rng=np.random.default_rng(4);x=rng.normal(size=(2000,3));y=x[:,0]*3-x[:,1]*2
        p=mlp(x[:1500],y[:1500],[x[1500:]],device='cpu')[0]
        self.assertLess(np.mean((p-y[1500:])**2),np.mean(y[1500:]**2)*.15)
