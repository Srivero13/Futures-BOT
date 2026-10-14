from decimal import Decimal
import unittest
from unittest.mock import patch
from diagnose_usdm_exposure import components, run


class ExposureTests(unittest.TestCase):
    def test_funding_receipt_can_be_outweighed_by_price_loss(self):
        r=components('2500','2600','-1.3715328575937172')
        self.assertEqual(Decimal(r['short_one_eth']['combined_before_trading_costs']),Decimal('-98.6284671424062828'))
        self.assertEqual(sum(Decimal(x['combined_before_trading_costs']) for x in r.values()),0)

    def test_flat_price_and_invalid_inputs(self):
        self.assertEqual(components('2500','2500','-2')['long_one_eth']['combined_before_trading_costs'],'-2')
        for o,c,f in [('0','1','0'),('1','NaN','0'),('1','2','Infinity')]:
            with self.assertRaises(ValueError):
                components(o,c,f)

    def test_seven_audits_and_fixed_reference_endpoints(self):
        reports={'inputs_sha256':{}}
        days=[[{'open':str(2500+i),'close':str(2501+i)}] for i in range(7)]
        with patch('diagnose_usdm_exposure.audit',return_value=reports) as a, patch('diagnose_usdm_exposure.candles',side_effect=days), patch('diagnose_usdm_exposure.diagnose',return_value={'events':21,'long_funding_cashflow':'-2','inputs_sha256':{}}):
            r=run('first','batch','spot','funding')
        self.assertEqual(a.call_count,7)
        self.assertEqual(r['opening_trade_price'],'2500')
        self.assertEqual(r['closing_trade_price'],'2507')
        self.assertEqual(r['scenarios']['long_one_eth']['combined_before_trading_costs'],'5')
        self.assertFalse(r['approved'])

    def test_audit_failure_stops_before_funding(self):
        with patch('diagnose_usdm_exposure.audit',side_effect=ValueError('bad')), patch('diagnose_usdm_exposure.diagnose') as funding:
            with self.assertRaises(ValueError):
                run('first','batch','spot','funding')
            funding.assert_not_called()
