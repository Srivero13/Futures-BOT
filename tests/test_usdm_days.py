import copy
from pathlib import Path
import tempfile
import unittest
import json
from engine_v1.dataset import sha256
from summarize_usdm_days import summarize,run


class DailyTests(unittest.TestCase):
    def scenario(self):
        return dict(mark_minutes=2,terminal_reconciled=True,terminal_net_pnl='3',
                    max_sampled_drawdown_quote='2',minimum_sampled_pnl_quote='-2',
                    path=[dict(timestamp_ms=86340000,kind='entry_fee_only',pnl='-2'),
                          dict(timestamp_ms=86399999,kind='mark_close',pnl='5'),
                          dict(timestamp_ms=86459999,kind='mark_close',pnl='4'),
                          dict(timestamp_ms=86460000,kind='realized_exit',pnl='3')])

    def test_midnight_continuity_and_costs_reconcile(self):
        r=summarize(self.scenario())
        self.assertEqual([d['net_change'] for d in r['daily']],['5','-2'])
        self.assertEqual(r['daily'][1]['opening_cumulative_pnl'],'5')
        self.assertEqual(r['terminal_net_pnl'],'3')
        self.assertEqual(r['net_excluding_best_day_change'],'-2')
        self.assertEqual(r['positive_days'],1)

    def test_nonfinite_gaps_and_false_totals_rejected(self):
        for change in ('nan','gap','total','drawdown'):
            s=copy.deepcopy(self.scenario())
            if change=='nan': s['path'][1]['pnl']='NaN'
            elif change=='gap': s['path'][1]['timestamp_ms']+=1
            elif change=='total': s['terminal_net_pnl']='4'
            else: s['max_sampled_drawdown_quote']='1'
            with self.assertRaises(ValueError): summarize(s)

    def test_source_hashes_checked(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';source.write_text('data')
            report=root/'report.json'
            report.write_text(json.dumps(dict(approved=False,symbol='ETHUSDT',
                inputs_sha256={str(source):sha256(source)},
                scenarios={k:self.scenario() for k in ('long_one_eth','short_one_eth')})))
            self.assertTrue(run(report)['scenarios']['long_one_eth']['daily_sum_reconciled'])
            source.write_text('changed')
            with self.assertRaises(ValueError): run(report)
