from decimal import Decimal as D
import unittest
from diagnose_execution_microstructure import Diagnostic,costs


class MicroExecutionTests(unittest.TestCase):
    def model(self):
        return {'frozen_at_wall_ns':0,'training_forecast_bucket_cuts':[.1],
                'mean':[0,0,0],'scale':[1,1,1],'coefficients':[1,0,0,0]}

    def feed(self,s,t,q=None):
        s.accept({'receipt_monotonic_ns':int(t*1e9),'receipt_wall_ns':int(t*1e9)+1},
                 q or tuple(map(D,['99','101','10','10'])))

    def test_cost_identity_and_depth(self):
        q=tuple(map(D,['99','101','10','10']))
        r=costs(q,q)
        self.assertLess(D(r['net_pnl']),0)
        self.assertEqual(D(r['midpoint_pnl']),0)
        self.assertAlmostEqual(float(D(r['midpoint_pnl'])-D(r['spread_slippage_cost'])-D(r['fees'])),float(r['net_pnl']))
        self.assertIsNone(costs(tuple(map(D,['99','101','10','.0001'])),q))

    def test_delayed_entry_holding_and_boundary(self):
        s=Diagnostic(self.model())
        for i in range(14):self.feed(s,i*.5)
        self.assertEqual(len(s.trades),1)
        self.assertEqual(s.trades[0]['actual_entry_delay_ms'],500)
        self.assertEqual(s.trades[0]['exit_ns']-s.trades[0]['entry_ns'],5_000_000_000)
        s=Diagnostic(self.model())
        for i in range(4):self.feed(s,i*.5)
        s.accept({'receipt_wall_ns':2_000_000_001},None)
        self.assertEqual(s.summary()['unresolved_positions'],1)
        self.assertEqual(s.trades,[])

    def test_late_entry_cancelled_and_freeze_guard(self):
        s=Diagnostic(self.model())
        for t in (0,.5,1,1.8):self.feed(s,t)
        self.assertEqual(s.counts['cancelled_entry_late'],1)
        s.model['frozen_at_wall_ns']=100
        with self.assertRaises(ValueError):s.accept({'receipt_wall_ns':99},None)
