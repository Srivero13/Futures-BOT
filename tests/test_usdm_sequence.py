import copy
from decimal import Decimal
import unittest
from usdm_sequence_accounting import account_sequence


class SequenceTests(unittest.TestCase):
    def inputs(self):
        trades=[dict(id='long',quantity='1',entry_reference='100',exit_reference='110',entry_ms=0,exit_ms=360000),
                dict(id='short',quantity='-2',entry_reference='110',exit_reference='100',entry_ms=600000,exit_ms=960000)]
        marks=[dict(open_ms=t,close='100',low='100',high='100') for t in range(0,960000,60000)]
        events=[dict(funding_time_ms=t,mark_price='100',funding_rate='0.01') for t in (180000,480000,780000)]
        return trades,marks,events

    def test_long_short_flat_funding_and_costs(self):
        r=account_sequence(*self.inputs(),'0','0')
        self.assertEqual(Decimal(r['net_pnl']),Decimal('31'))
        self.assertEqual(Decimal(r['funding_cashflow']),Decimal('1'))
        self.assertEqual(r['assigned_funding_events'],2)
        self.assertEqual(r['unassigned_funding_events'],1)
        self.assertEqual(Decimal(r['path'][8]['cumulative_pnl']),Decimal('9'))
        costed=account_sequence(*self.inputs(),'5','2')
        self.assertLess(Decimal(costed['net_pnl']),Decimal('31'))
        self.assertTrue(costed['accounting_reconciled'])

    def test_drawdown_carries_previous_peak_across_trades(self):
        t,m,e=self.inputs()
        t[0]['exit_reference']='90';t[1]['exit_reference']='120'
        r=account_sequence(t,m,[],'0','0')
        self.assertEqual(Decimal(r['net_pnl']),Decimal('-30'))
        self.assertEqual(Decimal(r['max_sampled_drawdown_quote']),Decimal('40'))

    def test_overlap_duplicate_id_and_missing_marks_fail(self):
        for case in ('overlap','id','gap','funding'):
            t,m,e=copy.deepcopy(self.inputs())
            if case=='overlap': t[1]['entry_ms']=360000
            elif case=='id': t[1]['id']='long'
            elif case=='gap': m.pop(1)
            else: e.append(e[-1])
            with self.assertRaises(ValueError): account_sequence(t,m,e,'5','2')

    def test_no_trades_no_fabricated_profit(self):
        r=account_sequence([],[],[],'5','2')
        self.assertEqual(r['net_pnl'],'0');self.assertEqual(r['closed_trades'],0)
        self.assertFalse(r['approved'])

    def test_ambiguous_settlement_and_float_quantity_fail(self):
        t,m,e=self.inputs()
        e[0]['funding_time_ms']=60000
        with self.assertRaises(ValueError): account_sequence(t,m,e,'5','2')
        t,m,e=self.inputs();t[0]['quantity']=1.0
        with self.assertRaises(ValueError): account_sequence(t,m,e,'5','2')

    def test_ohlc_bound_carries_previous_trade_peak_without_summing(self):
        trades, marks, _ = self.inputs()
        for trade in trades:
            trade.update(quantity='1', entry_reference='100', exit_reference='100')
        marks[0]['high']='130'
        marks[10]['low']='70'
        result=account_sequence(trades,marks,[],'0','0')
        self.assertEqual(Decimal(result['max_sampled_drawdown_quote']),Decimal('0'))
        self.assertEqual(Decimal(result['ohlc_drawdown_upper_bound_quote']),Decimal('60'))
        self.assertEqual(Decimal(result['ohlc_pnl_lower_bound_quote']),Decimal('-30'))
        # Two identical 30-unit excursions must not be added as 60.
        marks[10]['low']='100';marks[10]['high']='130'
        result=account_sequence(trades,marks,[],'0','0')
        self.assertEqual(Decimal(result['ohlc_drawdown_upper_bound_quote']),Decimal('30'))

    def test_bounds_contain_sampled_path_for_both_directions_with_costs(self):
        result=account_sequence(*self.inputs(),'5','2')
        self.assertGreaterEqual(Decimal(result['ohlc_drawdown_upper_bound_quote']),
                                Decimal(result['max_sampled_drawdown_quote']))
        self.assertLessEqual(Decimal(result['ohlc_pnl_lower_bound_quote']),
                             min(Decimal(p['cumulative_pnl']) for p in result['path']))
        empty=account_sequence([],[],[],'5','2')
        self.assertEqual(empty['ohlc_drawdown_upper_bound_quote'],'0')
        self.assertEqual(empty['ohlc_pnl_lower_bound_quote'],'0')
