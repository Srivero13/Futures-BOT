import unittest
from decimal import Decimal as D
from diagnose_weekly_btc_risk import replay


def bar(t, opening=100, high=100, low=100, close=100):
    return dict(timestamp=t, open=str(opening), high=str(high), low=str(low), close=str(close))


def scenario(trades, cash):
    return dict(trades=trades, ending_cash=str(cash), net_pnl=str(cash-1000))


def trade(entry, exit_time, price=100):
    return dict(entry_ms=entry, exit_ms=exit_time, entry_price='100', entry_outlay='100',
                quantity='1', exit_price=str(price), exit_fill=str(price), exit_fee='0')


class RiskTests(unittest.TestCase):
    def test_extrema_bound_and_exit_open(self):
        rows=[bar(0,high=150,low=50),bar(60000,high=1000,low=1)]
        result=replay(rows, {'base':scenario([trade(0,60000)],1000)},0,120000)['base']
        self.assertEqual(result['max_minute_sampled_drawdown_pct'],0)
        self.assertAlmostEqual(float(result['ohlc_drawdown_upper_bound_pct']),100/1050*100)
        self.assertEqual(result['ohlc_equity_lower_bound'],950)
        self.assertEqual(result['held_minutes'],1)

    def test_peak_carries_across_trades(self):
        rows=[bar(0,high=200,close=200),bar(60000),bar(120000,low=50,close=50),bar(180000)]
        result=replay(rows,{'base':scenario([trade(0,60000),trade(120000,180000)],1000)},0,240000)['base']
        self.assertAlmostEqual(float(result['max_minute_sampled_drawdown_pct']),150/1100*100)
        self.assertEqual(result['max_minute_sampled_drawdown_pct'],result['ohlc_drawdown_upper_bound_pct'])

    def test_missing_minute_and_changed_terminal_fail(self):
        s={'base':scenario([trade(0,60000)],1000)}
        with self.assertRaises(ValueError): replay([bar(0)],s,0,120000)
        s['base']['ending_cash']='1001'
        with self.assertRaises(ValueError): replay([bar(0),bar(60000)],s,0,120000)

    def test_reference_mismatch_and_overlap_fail(self):
        s={'base':scenario([trade(0,60000,101)],1001)}
        with self.assertRaises(ValueError): replay([bar(0),bar(60000)],s,0,120000)
        s={'base':scenario([trade(0,120000),trade(60000,180000)],1000)}
        with self.assertRaises(ValueError): replay([],s,0,240000)


if __name__=='__main__': unittest.main()
