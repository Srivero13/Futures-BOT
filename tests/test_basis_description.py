import math
import unittest
from unittest.mock import patch
from describe_basis_quotes import quote_metrics, describe_pairs, describe


def record(t=0, bid='100', ask='102'):
    return dict(kind='receipt_pair', paired_monotonic_ns=t,
        spot=dict(bid=bid, ask=ask), usdm=dict(bid='103', ask='105'))


class BasisDescriptionTests(unittest.TestCase):
    def test_bid_ask_levels_bracket_midpoint_and_spreads(self):
        r=quote_metrics(record())
        self.assertAlmostEqual(r['futures_bid_vs_spot_ask_log_bps'],10000*math.log(103/102))
        self.assertLess(r['futures_bid_vs_spot_ask_log_bps'],r['midpoint_basis_log_bps'])
        self.assertGreater(r['futures_ask_vs_spot_bid_log_bps'],r['midpoint_basis_log_bps'])
        equal=record(bid='103',ask='105')
        self.assertEqual(quote_metrics(equal)['midpoint_basis_log_bps'],0)
        self.assertLess(quote_metrics(equal)['futures_bid_vs_spot_ask_log_bps'],0)

    def test_first_pair_only_and_missing_seconds_not_forward_filled(self):
        a=record(10); b=record(100,bid='1',ask='2'); c=record(3_000_000_010)
        result=describe_pairs([a,b,c])
        self.assertEqual(result['sampled_seconds'],2)
        self.assertEqual(result['empty_buckets_within_pair_span'],2)
        self.assertEqual(result['metrics']['midpoint_basis_log_bps']['mean'],quote_metrics(a)['midpoint_basis_log_bps'])
        with self.assertRaises(ValueError): describe_pairs([])
        with self.assertRaises(ValueError): describe_pairs([c,a])

    def test_failed_audit_stops_description(self):
        with patch('describe_basis_quotes.audit',side_effect=ValueError('damaged')):
            with self.assertRaisesRegex(ValueError,'damaged'): describe('unused')
