from decimal import Decimal as D
import unittest
from diagnose_execution_microstructure import costs
from attribute_micro_costs import analyze


class CostAttributionTests(unittest.TestCase):
    def report(self,entry,exit):
        trade=costs(tuple(map(D,entry)),tuple(map(D,exit)))
        return {'protocol':{'slippage_bps_per_side':2,'fee_bps_per_side':10},'closed_trades':[trade],
            'summary':{'closed_trades':1,'unresolved_positions':2,'closed_trade_totals':{k:trade[k] for k in ('midpoint_pnl','fees','net_pnl','spread_slippage_cost')}}}

    def test_constant_market_spread_and_slippage_separate(self):
        r=self.report(['99','101','10','10'],['99','101','10','10']);s=analyze(r)
        self.assertLess(D(s['zero_slippage_zero_fee_net']),0)
        self.assertFalse(s['nonnegative_fee_can_break_even_without_slippage'])
        self.assertGreater(D(s['totals']['observed_spread_cost']),0)
        self.assertGreater(D(s['totals']['assumed_slippage_cost']),0)
        self.assertEqual(s['unresolved_positions'],2)
        r['closed_trades'][0]['fees']='0'
        with self.assertRaises(ValueError):analyze(r)

    def test_favorable_move_and_break_even_identity(self):
        s=analyze(self.report(['99','101','10','10'],['103','105','10','10']))
        fee=D(s['zero_slippage_break_even_fee_bps_per_side'])
        gross=D(s['zero_slippage_zero_fee_net']);turnover=D(s['totals']['reference_turnover'])
        self.assertGreater(fee,0)
        self.assertAlmostEqual(float(gross),float(turnover*fee/10000))
