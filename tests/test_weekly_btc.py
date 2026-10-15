from decimal import Decimal as D, localcontext
import unittest
from research_weekly_btc import build_schedule, simulate, START, MINUTE, WEEK


def rows(start,end):
    t=start-WEEK-MINUTE
    while t<end:
        close='100' if t==start-WEEK-MINUTE else '110'
        yield dict(timestamp=t,open='120',close=close)
        t+=MINUTE


class WeeklyBtcTests(unittest.TestCase):
    def test_closed_week_signal_and_delayed_open(self):
        end=START+24*60*MINUTE
        decisions,events=build_schedule(rows(START,end),START,end)
        self.assertEqual(len(decisions),1)
        self.assertEqual(decisions[0]['prior_week_close'],'100')
        self.assertEqual(decisions[0]['last_week_close'],'110')
        self.assertTrue(decisions[0]['long'])
        self.assertEqual(events[0]['timestamp'],START+MINUTE)
        self.assertEqual(events[0]['price'],D('120'))
        self.assertEqual(events[-1]['timestamp'],end-MINUTE)

    def test_missing_warmup_or_interior_minute_rejected(self):
        end=START+24*60*MINUTE
        for missing in (START-WEEK-MINUTE,START-2*MINUTE,end-MINUTE):
            with self.subTest(missing=missing),self.assertRaises(ValueError):
                build_schedule((r for r in rows(START,end) if r['timestamp']!=missing),START,end)

    def test_unchanged_long_no_rebalance_and_stress_resizes(self):
        events=[dict(kind='target',timestamp=START+MINUTE,price=D('100'),long=True),
                dict(kind='target',timestamp=START+WEEK+MINUTE,price=D('150'),long=True),
                dict(kind='mark',timestamp=START+WEEK+2*MINUTE,price=D('140')),
                dict(kind='terminal',timestamp=START+2*WEEK,price=D('100'))]
        base=simulate(events,'2');stress=simulate(events,'3')
        self.assertEqual(base['closed_trades'],1)
        self.assertTrue(base['trades'][0]['forced_terminal'])
        self.assertEqual(base['trades'][0]['entry_outlay'],100)
        self.assertLess(stress['trades'][0]['quantity'],base['trades'][0]['quantity'])
        self.assertLess(stress['net_pnl'],base['net_pnl'])
        with localcontext() as ctx:
            ctx.prec=50
            self.assertLess(abs(base['reference_price_pnl']-base['fees']-base['assumed_impact_cost']-base['net_pnl']),D('1e-40'))

    def test_cash_and_buy_hold_have_distinct_exposure(self):
        events=[dict(kind='target',timestamp=START+MINUTE,price=D('100'),long=False),
                dict(kind='terminal',timestamp=START+WEEK,price=D('110'))]
        cash=simulate(events,'2');hold=simulate(events,'2',True)
        self.assertEqual(cash['net_pnl'],0);self.assertEqual(cash['fees'],0)
        self.assertEqual(hold['closed_trades'],1);self.assertGreater(hold['net_pnl'],0)
