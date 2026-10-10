from decimal import Decimal
import unittest
from funding_cashflows import funding_cashflow, event_exposure


class CashflowTests(unittest.TestCase):
    def test_positive_negative_and_zero_rates(self):
        self.assertEqual(funding_cashflow('2','2500','0.0001'),Decimal('-0.5'))
        self.assertEqual(funding_cashflow('-2','2500','0.0001'),Decimal('0.5'))
        self.assertEqual(funding_cashflow('2','2500','-0.0001'),Decimal('0.5'))
        self.assertEqual(funding_cashflow('2','2500','0'),0)
        self.assertEqual(funding_cashflow('0','2500','0.0001'),0)

    def test_decimal_inputs_and_missing_mark(self):
        for args in (('1',None,'0.1'),('1','0','0.1'),('NaN','2500','0.1'),
                     (1.0,'2500','0.1'),('1','2500','Infinity')):
            with self.assertRaises(ValueError):
                funding_cashflow(*args)

    def test_boundaries_are_ambiguous_and_original_ms_matter(self):
        self.assertEqual(event_exposure(0,1000000,0),'ambiguous')
        self.assertEqual(event_exposure(0,1000000,1000001),'ambiguous')
        self.assertEqual(event_exposure(0,1000000,60000),'ambiguous')
        self.assertEqual(event_exposure(0,1000000,60001),'held')
        self.assertEqual(event_exposure(0,1000000,1100000),'not_held')
        with self.assertRaises(ValueError):
            event_exposure(1,0,5)

    def test_audited_report_reconciles_both_sides(self):
        import test_usdm_funding_audit
        from diagnose_funding_cashflows import diagnose
        fixture=test_usdm_funding_audit.FundingAuditTests()
        fixture.setUp()
        try:
            r=diagnose(fixture.root,'ETHUSDT',fixture.start,fixture.end,fixture.reserve)
            self.assertEqual(r['events'],21)
            self.assertEqual(Decimal(r['long_funding_cashflow']),Decimal('-5.25'))
            self.assertEqual(Decimal(r['short_funding_cashflow']),Decimal('5.25'))
            self.assertFalse(r['approved'])
        finally:
            fixture.doCleanups()
