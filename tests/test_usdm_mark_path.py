import unittest
from diagnose_usdm_roundtrip import roundtrip
from diagnose_usdm_mark_path import mark_path


class MarkPathTests(unittest.TestCase):
    def setup_path(self, q='1'):
        events=[dict(funding_time_ms=180001,mark_price='100',funding_rate='0.001')]
        marks=[dict(open_ms=t,close=c,low=c,high=c) for t,c in zip(range(0,360000,60000),['100','102','98','101','99','100'])]
        s=roundtrip(q,'100','101',0,360000,events,'5','2')
        return s,marks,events

    def test_long_short_reconcile_and_funding_timing(self):
        for q in ('1','-1'):
            s,m,e=self.setup_path(q)
            r=mark_path(s,m,e,'5')
            self.assertEqual(r['terminal_net_pnl'],s['scenario_net_pnl'])
            self.assertEqual(r['mark_minutes'],6)
            self.assertEqual(len(r['path']),8)
        s,m,e=self.setup_path()
        r=mark_path(s,m,e,'5')
        self.assertEqual(r['path'][3]['pnl'],'-2.07001')
        self.assertEqual(r['path'][4]['pnl'],'0.82999')
        self.assertEqual(r['max_sampled_drawdown_quote'],'4.00000')

    def test_missing_duplicate_bad_marks_rejected(self):
        s,m,e=self.setup_path()
        for bad in (m[:-1],m[1:],m[:2]+[m[1]]+m[2:], [dict(row,close='NaN') for row in m]):
            with self.assertRaises(ValueError): mark_path(s,bad,e,'5')

    def test_ambiguous_and_duplicate_funding_rejected(self):
        s,m,e=self.setup_path()
        for bad in (e+e,[dict(e[0],funding_time_ms=1)]):
            with self.assertRaises(ValueError): mark_path(s,m,bad,'5')
        s['accounting_resolved_for_supplied_events']=False
        with self.assertRaises(ValueError): mark_path(s,m,e,'5')

    def test_terminal_mismatch_rejected(self):
        s,m,e=self.setup_path()
        s['scenario_net_pnl']='999'
        with self.assertRaises(ValueError): mark_path(s,m,e,'5')

    def test_high_low_excursion_hidden_by_closes(self):
        for q in ('1', '-1'):
            s=roundtrip(q,'100','100',0,180000,[],'0','0')
            m=[dict(open_ms=t,close='100',low='90',high='110') for t in range(0,180000,60000)]
            r=mark_path(s,m,[],'0')
            self.assertEqual(r['max_sampled_drawdown_quote'],'0')
            self.assertEqual(r['ohlc_drawdown_upper_bound_quote'],'20')
            self.assertEqual(r['ohlc_pnl_lower_bound_quote'],'-10')

    def test_funding_order_envelope_contains_intermediate_debit(self):
        e=[dict(funding_time_ms=180001,mark_price='100',funding_rate='0.05'),
           dict(funding_time_ms=180002,mark_price='100',funding_rate='-0.05')]
        s=roundtrip('1','100','100',0,360000,e,'0','0')
        m=[dict(open_ms=t,close='100',low='100',high='100') for t in range(0,360000,60000)]
        r=mark_path(s,m,e,'0')
        self.assertEqual(r['max_sampled_drawdown_quote'],'0')
        self.assertEqual(r['ohlc_drawdown_upper_bound_quote'],'5.00')
        self.assertEqual(r['ohlc_pnl_lower_bound_quote'],'-5.00')

    def test_reversed_or_nonfinite_extrema_rejected(self):
        s,m,e=self.setup_path()
        for low,high in [('103','99'),('NaN','102'),('0','102')]:
            bad=[dict(row,low=low,high=high) for row in m]
            with self.assertRaises(ValueError): mark_path(s,bad,e,'5')
