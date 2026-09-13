import unittest
from dataclasses import replace
from backtest import Params,simulate,validate_candles

def candles(prices):
    return [dict(timestamp=1735689600+i*300,open=p,high=p,low=p,close=p,volume=100) for i,p in enumerate(prices)]

class ResearchTests(unittest.TestCase):
    def test_flat_roundtrip_cost(self):
        p=Params(capital=1000,notional=100,fee_bps=10,slippage_bps=0,spread_bps=0)
        r=simulate(candles([100]*24),p,'hold')
        self.assertAlmostEqual(r['summary']['net_pnl'],-.2,places=8)
        self.assertAlmostEqual(r['summary']['fees'],.2,places=8)

    def test_cash_zero(self):
        r=simulate(candles([100]*24),strategy='cash')
        self.assertEqual(r['summary']['net_pnl'],0)
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_hourly_and_realized_reconcile(self):
        r=simulate(candles([100,101,99,102]*15),Params(fast=2,slow=3))
        self.assertAlmostEqual(sum(x['pnl'] for x in r['hourly']),r['summary']['net_pnl'])
        self.assertAlmostEqual(sum(x['net_pnl'] for x in r['trades']),r['summary']['net_pnl'])

    def test_overhead(self):
        r=simulate(candles([100]*24),Params(hourly_overhead=.1),'cash')
        self.assertAlmostEqual(r['summary']['net_pnl'],-.2)

    def test_no_same_bar_signal_fill(self):
        p=Params(fast=1,slow=2,fee_bps=0,slippage_bps=0,spread_bps=0)
        r=simulate(candles([100,200,300,300]),p)
        self.assertEqual(r['trades'][0]['entry_price'],300)

    def test_future_changes_do_not_change_past(self):
        a=candles([100,101,102,101]*20)
        b=a[:50]+candles([1000]*30)
        for i in range(50,80): b[i]['timestamp']=a[i]['timestamp']
        p=Params(fast=2,slow=4)
        x=simulate(a,p); y=simulate(b,p)
        self.assertEqual(x['equity'][:50],y['equity'][:50])

    def test_duplicates_and_gaps_rejected(self):
        a=candles([100]*3)
        with self.assertRaises(ValueError): validate_candles([a[0],a[0]])
        with self.assertRaises(ValueError): validate_candles([a[0],a[2]])

    def test_gap_loss_exceeds_stop(self):
        p=Params(fast=1,slow=2,max_drawdown=.01)
        r=simulate(candles([100,101,102,1,1]),p)
        self.assertTrue(r['summary']['halted'])
        self.assertLess(r['summary']['net_pnl'],-10)

    def test_rounding_and_minimum(self):
        r=simulate(candles([100]*3),Params(qty_step='1',notional=5),'hold')
        self.assertEqual(r['summary']['closed_trades'],0)

    def test_negative_cost_invalid(self):
        with self.assertRaises(ValueError): simulate(candles([100]*3),Params(fee_bps=-1))

if __name__=='__main__': unittest.main()
