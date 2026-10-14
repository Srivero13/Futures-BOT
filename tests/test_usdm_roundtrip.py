import unittest
from decimal import Decimal
from diagnose_usdm_roundtrip import roundtrip


class RoundtripTests(unittest.TestCase):
    def calc(self,q='1',events=None,fee='5',impact='2'):
        return roundtrip(q,'100','110',0,1000000,events or [],fee,impact)

    def test_long_and_short_adverse_costs(self):
        a,b=self.calc(),self.calc('-1')
        self.assertEqual(Decimal(a['assumed_price_impact_cost']),Decimal('.042'))
        self.assertEqual(Decimal(b['assumed_price_impact_cost']),Decimal('.042'))
        for r in (a,b):
            self.assertEqual(Decimal(r['scenario_net_pnl']),Decimal(r['reference_price_pnl'])-Decimal(r['assumed_price_impact_cost'])-Decimal(r['assumed_fees']))

    def test_funding_only_while_held_and_missing_mark_fails(self):
        e=[dict(funding_time_ms=-100000,mark_price='100',funding_rate='.001'),
           dict(funding_time_ms=500000,mark_price='100',funding_rate='.001')]
        r=self.calc(events=e,fee='0',impact='0')
        self.assertEqual(r['held_funding_events'],1)
        self.assertEqual(r['outside_funding_events'],1)
        self.assertEqual(Decimal(r['scenario_net_pnl']),Decimal('9.9'))
        e[1]['mark_price']=None
        with self.assertRaises(ValueError):
            self.calc(events=e)

    def test_boundary_ambiguity_withholds_net(self):
        r=self.calc(events=[dict(funding_time_ms=1,mark_price='100',funding_rate='.001')])
        self.assertIsNone(r['scenario_net_pnl'])
        self.assertFalse(r['accounting_resolved_for_supplied_events'])

    def test_invalid_costs_and_duplicate_events_rejected(self):
        for fee in ('-1','NaN','10000'):
            with self.assertRaises(ValueError):
                self.calc(fee=fee)
        e=dict(funding_time_ms=500000,mark_price='100',funding_rate='.001')
        with self.assertRaises(ValueError):
            self.calc(events=[e,e])
