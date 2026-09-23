from decimal import Decimal as D
import math
import unittest
from diagnose_delayed_execution import DelayedDiagnostic,cost_barrier
from diagnose_execution_microstructure import costs


class DelayedExecutionTests(unittest.TestCase):
    def model(self,forecast=1):
        return {'frozen_at_wall_ns':0,'training_forecast_bucket_cuts':[.1],
                'mean':[0,0,0],'scale':[1,1,1],'coefficients':[forecast,0,0,0]}

    def feed(self,s):
        for i in range(14):
            s.accept({'receipt_monotonic_ns':i*500_000_000,'receipt_wall_ns':i*500_000_000+1},
                     tuple(map(D,['99','101','10','10'])))

    def test_cost_gate_does_not_force_weak_forecasts(self):
        top=DelayedDiagnostic(self.model(),False);gated=DelayedDiagnostic(self.model(),True)
        self.feed(top);self.feed(gated)
        self.assertEqual(len(top.trades),1);self.assertEqual(len(gated.trades),0)
        self.assertEqual(gated.summary()['training_top_bucket_threshold_log_bps'],.1)
        self.assertAlmostEqual(gated.summary()['effective_entry_threshold_log_bps'],24,places=4)
        strong=DelayedDiagnostic(self.model(25),True);self.feed(strong)
        self.assertEqual(len(strong.trades),1)

    def test_barrier_matches_cost_ledger_without_double_spread(self):
        entry=tuple(map(D,['99','100','10','10']))
        exit_bid=D(str(100*math.exp(cost_barrier()/10000)))
        result=costs(entry,(exit_bid,exit_bid+D('1'),D('10'),D('10')))
        self.assertAlmostEqual(float(result['net_pnl']),0,places=10)

    def test_unresolved_not_counted_as_closed(self):
        s=DelayedDiagnostic(self.model(25),True)
        for i in range(4):s.accept({'receipt_monotonic_ns':i*500_000_000,'receipt_wall_ns':i*500_000_000+1},tuple(map(D,['99','101','10','10'])))
        s.accept({'receipt_wall_ns':3_000_000_000},None)
        self.assertEqual(s.summary()['unresolved_positions'],1)
        self.assertEqual(s.summary()['closed_trades'],0)
        self.assertFalse(s.summary()['complete_execution_result'])
