import copy
import unittest
from usdm_sequence_accounting import account_sequence
from review_usdm_experiment import review,FIELDS


class ReviewTests(unittest.TestCase):
    def report(self,exit_price='99'):
        t=[dict(id='a',quantity='1',entry_reference='100',exit_reference=exit_price,entry_ms=0,exit_ms=180000)]
        m=[dict(open_ms=i*60000,low='100',high='100',close='100') for i in range(3)]
        ledger=account_sequence(t,m,[],'5','2')
        summary={k:ledger[k] for k in FIELDS}
        summary.update(closed_trades=1,long_trades=1,short_trades=0,net_pnl_excluding_best_trade='0')
        return dict(experiment='UM01',approved=False,status='development_only',ledger=ledger,summary=summary)

    def test_loss_is_rejected_before_costs(self):
        r=review(self.report())
        self.assertEqual(r['status'],'rejected_development')
        self.assertEqual(r['zero_fee_zero_impact_pnl'],'-1')

    def test_profit_is_never_approved(self):
        r=review(self.report('110'))
        self.assertEqual(r['status'],'requires_independent_validation')
        self.assertFalse(r['approved'])

    def test_inconsistent_saved_evidence_rejected(self):
        for target in ('summary','cumulative','components'):
            d=copy.deepcopy(self.report())
            if target=='summary': d['summary']['net_pnl']='0'
            elif target=='cumulative': d['ledger']['trades'][0]['cumulative_realized_pnl']='0'
            else: d['ledger']['trades'][0]['accounting']['assumed_fees']='NaN'
            with self.assertRaises(ValueError): review(d)

    def breakout_report(self):
        from datetime import date
        from download_usdm_funding import timestamp
        from research_usdm_bundle import weekly_summary
        from decimal import Decimal
        d=self.report();d['experiment']='UM02'
        d['protocol']=dict(fee_bps_per_side='5',impact_bps_per_side='2')
        d['summary']['net_excluding_best_trade']=d['summary'].pop('net_pnl_excluding_best_trade')
        a=d['ledger']['trades'][0]['accounting']
        a['entry_ms']+=timestamp(date(2026,8,8));a['exit_ms']+=timestamp(date(2026,8,8))
        d['summary']['exit_week_totals']=weekly_summary(d['ledger'])
        s=d['summary']
        s['extra_1bps_impact_per_side_net_pnl']=str(Decimal(s['net_pnl'])-Decimal(s['assumed_price_impact_cost'])/2+Decimal(s['reference_price_pnl'])*Decimal('0.00000005'))
        return d

    def test_breakout_stress_and_identity_are_preserved(self):
        r=review(self.breakout_report())
        self.assertEqual(r['experiment'],'UM02')
        self.assertEqual(r['status'],'rejected_development')
        self.assertIn('Nonpositive net P&L with extra 1 bps impact per side',r['reasons'])

    def test_breakout_changed_stress_or_week_rejected(self):
        d=self.breakout_report();d['summary']['extra_1bps_impact_per_side_net_pnl']='0'
        with self.assertRaises(ValueError): review(d)
        d=self.breakout_report();d['summary']['exit_week_totals'][0]['closed_trades']=2
        with self.assertRaises(ValueError): review(d)
