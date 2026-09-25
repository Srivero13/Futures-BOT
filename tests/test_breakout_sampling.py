from decimal import Decimal
import unittest
from audit_breakout_sampling import audit
from research_daily_breakout import signal


def rows(n=1800):
    return [dict(timestamp=i*60000, high=str(100+i), close=str(100+i)) for i in range(n)]


class BreakoutSamplingTests(unittest.TestCase):
    def test_matches_brute_force_and_original_hourly_rule(self):
        data = rows()
        # Old highs, plateaus and strict comparisons exercise deque expiration.
        data[20]['high'] = '2000'
        data[1550]['high'] = '3000'
        result = audit(data, 1500*60000, 1700*60000)
        total = hourly = 0
        for decision in range(1500, 1700):
            i = decision-1
            history = data[i-1440:i+1]
            brute = Decimal(data[i]['close']) > max(Decimal(r['high']) for r in history[:-1])
            total += brute
            if decision % 60 == 0:
                hourly += signal(history, decision*60000)
        self.assertEqual(result['breakout_minutes'], total)
        self.assertEqual(result['hourly_breakout_observations'], hourly)
        self.assertEqual(result['evaluated_minutes'], 200)
        self.assertEqual(sum(result['monthly'][0]['breakouts_by_utc_minute']), total)

    def test_no_future_dependency(self):
        data = rows()
        first = audit(data, 1500*60000, 1600*60000)
        for row in data[1599:]:
            row.update(close='1', high='99999')
        self.assertEqual(first, audit(data, 1500*60000, 1600*60000))

    def test_gaps_missing_warmup_and_truncated_interval(self):
        for data in (rows()[100:], rows()[:1550], rows()[:1550]+rows()[1551:]):
            with self.assertRaises(ValueError):
                audit(data, 1500*60000, 1700*60000)

    def test_flat_market_no_ratio(self):
        data = rows()
        for row in data:
            row.update(close='100', high='100')
        result = audit(data, 1500*60000, 1700*60000)
        self.assertEqual(result['breakout_minutes'], 0)
        self.assertIsNone(result['hourly_share_of_breakout_observations'])
