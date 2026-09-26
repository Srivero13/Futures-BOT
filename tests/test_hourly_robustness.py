import copy
from dataclasses import asdict
from decimal import Decimal
import unittest

from backtest_v16 import Costs
from diagnose_hourly_robustness import analyze
from research_hourly_trend import evaluate


def fixture():
    rows = [dict(timestamp=i*60000, open='100', close='100', high='100',
                 low='100', volume='1') for i in range(240)]
    rows[59].update(close='102', high='102')
    rows[121].update(open='101', high='101')
    fold = evaluate(rows, 3600000, 240*60000, {'threshold': 0, 'end_ms': 3600000})
    fold['test_start'] = '2026-03-01'
    return {'protocol': {'hypothesis': '20-minute upward trend continuation over a 60-minute holding period',
                         'costs': asdict(Costs())}, 'folds': [fold],
            'summary': {'closed_trades': fold['summary']['closed_trades'],
                        'sum_independent_month_net_pnl': fold['summary']['net_pnl']}}


class HourlyRobustnessTests(unittest.TestCase):
    def test_zero_stress_reconciles_and_best_removal(self):
        report = fixture()
        result = analyze(report)
        self.assertEqual(result['closed_trades'], 1)
        self.assertEqual(Decimal(result['net_pnl']), Decimal(report['summary']['sum_independent_month_net_pnl']))
        self.assertEqual(Decimal(result['net_pnl_excluding_best_trade']), 0)
        scenarios = result['slippage_scenarios']
        values = [Decimal(s['sum_independent_month_net_pnl']) for s in scenarios]
        self.assertAlmostEqual(values[0], Decimal(result['net_pnl']), places=25)
        self.assertTrue(all(a > b for a, b in zip(values, values[1:])))
        # A 1 bps extra impact on each side changes total by quantity times both
        # reference prices, with buy/sell fees included.
        trade = report['folds'][0]['trades'][0]
        q = Decimal(trade['quantity'])
        expected = q*Decimal('.0001')*(Decimal(100)*Decimal('1.001')+Decimal(101)*Decimal('.999'))
        self.assertAlmostEqual(values[0]-values[2], expected, places=20)

    def test_corrupt_accounting_costs_timing_and_duplicates_rejected(self):
        for key in ('net_pnl', 'fees', 'quantity', 'exit_ms'):
            report = fixture()
            report['folds'][0]['trades'][0][key] = 0
            with self.assertRaises(ValueError):
                analyze(report)
        report = fixture()
        report['folds'].append(copy.deepcopy(report['folds'][0]))
        with self.assertRaises(ValueError):
            analyze(report)
        report = fixture()
        report['protocol']['costs']['fee_bps'] = 5
        with self.assertRaises(ValueError):
            analyze(report)

    def test_no_trades(self):
        report = fixture()
        fold = report['folds'][0]
        fold['trades'] = []
        fold['summary'].update(closed_trades=0, net_pnl='0')
        report['summary'].update(closed_trades=0, sum_independent_month_net_pnl='0')
        result = analyze(report)
        self.assertIsNone(result['best_trade_net_pnl'])
        self.assertIsNone(result['positive_without_best_trade'])
