import copy
from decimal import Decimal
import unittest
from basis_cost_accounting import account


def scenario():
    leg=dict(fee_bps_per_execution='10',slippage_bps_per_execution='0',
        entry=dict(bid='100',ask='100'),exit=dict(bid='100',ask='100'))
    return dict(quantity_eth='1',direction='long_futures_short_spot',cost_source='Synthetic test',
                spot=copy.deepcopy(leg),futures=copy.deepcopy(leg))


class BasisCostTests(unittest.TestCase):
    def test_four_fees_at_actual_assumed_notionals(self):
        s=scenario();s['futures']['fee_bps_per_execution']='5'
        r=account(s)
        self.assertEqual(len(r['executions']),4)
        self.assertEqual(Decimal(r['assumed_fees']),Decimal('.3'))
        self.assertEqual(Decimal(r['subtotal_bps_of_entry_spot_notional']),-30)
        s['futures']['exit']=dict(bid='110',ask='110')
        self.assertEqual(Decimal(account(s)['assumed_fees']),Decimal('.305'))

    def test_spreads_not_double_counted_and_slippage_adverse(self):
        s=scenario()
        for leg in ('spot','futures'):
            s[leg]['fee_bps_per_execution']='0'
            s[leg]['entry']['ask']='101';s[leg]['exit']['ask']='101'
        for side in ('long_spot_short_futures','long_futures_short_spot'):
            s['direction']=side
            r=account(s);self.assertEqual(Decimal(r['quote_reference_pnl']),-2)
            s['spot']['slippage_bps_per_execution']='1'
            r=account(s)
            self.assertEqual(Decimal(r['assumed_slippage_cost']),Decimal('.0201'))
            self.assertEqual(Decimal(r['subtotal_before_funding_and_financing']),Decimal('-2.0201'))

    def test_rejects_invalid_inputs(self):
        for key,value in [('quantity_eth','NaN'),('quantity_eth',1.0),('quantity_eth','0'),
                          ('direction','unknown'),('cost_source','')]:
            s=scenario();s[key]=value
            with self.assertRaises(ValueError): account(s)
        for value in ('-1','Infinity','10000'):
            s=scenario();s['spot']['fee_bps_per_execution']=value
            with self.assertRaises(ValueError): account(s)
