import json
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np
from engine_v1.core import Portfolio, Quote, Rules, dec, floor_step, break_even_bps
from engine_v1.latency import policy
from engine_v1.model import feature_matrix, fit_model, RidgeModel
from engine_v1.stream import FeedState, load_profile, rules_from_exchange


def quote(price='100', seq=1, ts=1000, symbol='BTCUSDT'):
    return Quote(symbol, dec(price), dec(price), dec('100'), dec('100'), ts, seq)


def accounts(n=1):
    return [{'id':str(i),'symbol':'BTCUSDT','capital':'1000','notional':'100'} for i in range(n)]


class AccountingTests(unittest.TestCase):
    def engine(self, n=1, path=':memory:', **kw):
        p=Portfolio(path, accounts(n), **kw);self.addCleanup(p.close);return p

    def test_reject_nonexact_nonfinite_input(self):
        for value in (0.1, True, 'NaN', 'Infinity'):
            with self.assertRaises(ValueError):dec(value)
        self.assertEqual(dec('0.1')+dec('0.2'),dec('0.3'))

    def test_quantity_rounds_down_non_power_of_ten(self):
        self.assertEqual(floor_step(dec('1.234'),dec('0.005')),dec('1.230'))

    def test_exact_roundtrip(self):
        p=self.engine(fee_bps='10',slip_bps='0')
        p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='buy')
        result=p.process({'BTCUSDT':quote('101',2,61000)},{'0':{'exit':True}},61000,event_id='sell')
        self.assertEqual(dec(result[0]['cash']),dec('1000.799'))
        self.assertEqual(dec(result[0]['realized']),dec('0.799'))
        self.assertEqual(dec(p.states()[0]['fees']),dec('0.201'))
        self.assertEqual(dec(p.states()[0]['qty']),0)

    def test_break_even_covers_both_sides(self):
        q=Quote('BTCUSDT',dec('99'),dec('101'),dec(1),dec(1),1,1)
        cost=break_even_bps(q,'10','2')
        future_bid=q.bid*(1+cost/10000)
        initial=q.ask*dec('1.0002')*dec('1.001')
        final=future_bid*dec('.9998')*dec('.999')
        self.assertLess(abs(initial-final),dec('1e-45'))

    def test_idempotent_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'ledger.sqlite3')
            p=Portfolio(path,accounts());p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='same')
            before=p.states();p.close()
            p=Portfolio(path,accounts())
            try:
                self.assertEqual(p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='same'),[])
                self.assertEqual(before,p.states())
            finally:p.close()

    def test_two_accounts_share_cap(self):
        p=self.engine(2,global_cap='120',fee_bps='0',slip_bps='0')
        p.process({'BTCUSDT':quote()},{str(i):{'enter':True} for i in range(2)},1000,event_id='both')
        self.assertEqual(sum(dec(a['qty'])*100 for a in p.states()),dec('120'))

    def test_cost_loss_blocks_second_account_in_same_transaction(self):
        p=self.engine(2,fee_bps='1000',slip_bps='0',daily_loss='0.001')
        events=p.process({'BTCUSDT':quote()},{'0':{'enter':True},'1':{'enter':True}},1000,event_id='both')
        self.assertEqual([e['action'] for e in events],['BUY','HOLD'])

    def test_stale_held_symbol_blocks_other_entry(self):
        p=self.engine(2)
        p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='one')
        before=p.states()
        e=p.process({'BTCUSDT':quote()},{'1':{'enter':True}},2001,event_id='late')
        self.assertEqual(e[0]['action'],'STALE_PORTFOLIO');self.assertEqual(before,p.states())

    def test_stale_and_future_quotes_cannot_enter(self):
        p=self.engine()
        for now in (999,2001):
            self.assertEqual(p.process({'BTCUSDT':quote()},{'0':{'enter':True}},now,event_id=str(now)),[])

    def test_out_of_order_rolls_back(self):
        p=self.engine();p.process({'BTCUSDT':quote(seq=5)},{},1000,event_id='first')
        before=p.states()
        with self.assertRaises(ValueError):p.process({'BTCUSDT':quote(seq=4)},{'0':{'enter':True}},1000,event_id='bad')
        self.assertEqual(before,p.states())

    def test_drawdown_exit_and_persistent_halt(self):
        p=self.engine(fee_bps='0',slip_bps='0',drawdown='0.005')
        p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='buy')
        e=p.process({'BTCUSDT':quote('90',2,2000)},{},2000,event_id='drop')
        self.assertEqual(e[0]['reason'],'risk')
        e=p.process({'BTCUSDT':quote('100',3,100000000)},{'0':{'enter':True}},100000000,event_id='nextday')
        self.assertEqual(e[0]['action'],'HOLD');self.assertTrue(p.states()[0]['halted'])

    def test_step_minimum_and_top_liquidity(self):
        p=self.engine(fee_bps='0',slip_bps='0')
        q=Quote('BTCUSDT',dec('100'),dec('100'),dec('2'),dec('2'),1000,1)
        e=p.process({'BTCUSDT':q},{'0':{'enter':True}},1000,event_id='a',rules={'BTCUSDT':Rules(step='0.03')})
        self.assertEqual(dec(e[0]['quantity']),dec('0.18'))

    def test_per_account_horizon(self):
        a=accounts();a[0]['horizon_ms']=60000;p=Portfolio(':memory:',a);self.addCleanup(p.close)
        p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='buy')
        e=p.process({'BTCUSDT':quote(seq=2,ts=61000)},{},61000,event_id='timeout',horizon_ms=300000)
        self.assertEqual(e[0]['action'],'SELL')


class TimingAndFeedTests(unittest.TestCase):
    def test_policy_rejects_insufficient_slow_unreliable(self):
        for samples,failures,attempts in [([20]*29,0,29),([1001]*30,0,30),([20]*30,3,33)]:
            self.assertFalse(policy(samples,failures,attempts)['eligible_for_paper_stream'])
        p=policy([100]*100,0,100)
        self.assertTrue(p['eligible_for_paper_stream']);self.assertEqual(p['minimum_decision_spacing_ms'],200)
        self.assertEqual(p['quote_deadline_ms'],300);self.assertEqual(p['minimum_horizon_ms'],60000)

    def test_profile_must_be_local_current_with_clock_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'p.json';p={'created_at_ms':1000,'location':'user-pc','endpoints':{'quote':policy([100]*100,0,100),'server_time':policy([100]*100,0,100)},'clock_estimate':{'uncertainty_ms':50,'offset_ms':0}}
            for endpoint in p['endpoints'].values():endpoint['samples']=[{'ok':True,'rtt_ms':100} for _ in range(100)]
            path.write_text(json.dumps(p));self.assertEqual(load_profile(path,1001),p)
            for key,value in [('location','development'),('created_at_ms',2000),('created_at_ms',-86400000)]:
                bad={**p,key:value};path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):load_profile(path,1001)

    def test_duplicate_book_and_reconnect(self):
        f=FeedState();d={'s':'BTCUSDT','u':10,'b':'100','a':'101','B':'2','A':'3'}
        self.assertTrue(f.accept_book(d,1000));self.assertFalse(f.accept_book(d,1001))
        f.healthy.add('BTCUSDT');f.reset_quotes();self.assertFalse(f.quotes);self.assertFalse(f.healthy)

    def test_candle_gap_discards_warmup(self):
        f=FeedState()
        def candle(i,closed=True):return {'s':'BTCUSDT','k':{'t':i*60000,'x':closed,'o':'100','h':'101','l':'99','c':'100','v':'1'}}
        self.assertFalse(f.accept_kline(candle(0,False)))
        for i in range(21):f.accept_kline(candle(i))
        self.assertIn('BTCUSDT',f.healthy)
        self.assertFalse(f.accept_kline(candle(20)))
        f.accept_kline(candle(22));self.assertNotIn('BTCUSDT',f.healthy);self.assertEqual(len(f.rows['BTCUSDT']),1)

    def test_exchange_lot_fallback(self):
        info={'filters':[{'filterType':'MARKET_LOT_SIZE','stepSize':'0'}, {'filterType':'LOT_SIZE','stepSize':'0.001','minQty':'0.001','maxQty':'100'}, {'filterType':'MIN_NOTIONAL','minNotional':'5'}]}
        self.assertEqual(rules_from_exchange(info).step,'0.001')


class ModelTests(unittest.TestCase):
    @staticmethod
    def rows(n=500):
        return [{'timestamp':i*60000,'open':str(100+math.sin(i/7)), 'close':str(100+math.sin(i/7)), 'high':'102','low':'98','volume':'100'} for i in range(n)]

    def test_features_are_causal_and_live_matches_batch(self):
        rows=self.rows();x=feature_matrix(rows)
        np.testing.assert_allclose(x[100],feature_matrix(rows[80:101])[-1])
        changed=rows[:101]+[{**r,'close':'10000','high':'10001'} for r in rows[101:]]
        np.testing.assert_allclose(x[:101],feature_matrix(changed)[:101],equal_nan=True)

    def test_holdout_cannot_change_fit_or_calibration(self):
        rows=self.rows();m=fit_model(rows,feature_matrix(rows),'BTCUSDT',3,300,400)
        changed=rows[:400]+[{**r,'open':'10000','close':'10000','high':'10001'} for r in rows[400:]]
        other=fit_model(changed,feature_matrix(changed),'BTCUSDT',3,300,400)
        self.assertEqual(m,other)
        self.assertTrue(all(math.isfinite(v) for v in m.coef))
        self.assertEqual(m.scale[4],1)  # Constant volume is safe.

    def test_model_roundtrip_checksum_and_ood(self):
        rows=self.rows();x=feature_matrix(rows);m=fit_model(rows,x,'BTCUSDT',1,300,400)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'m.json';m.save(path);loaded=RidgeModel.load(path)
            self.assertEqual(m.predict(x[100]),loaded.predict(x[100]))
            self.assertFalse(loaded.decision(np.full(6,1e10),dec('20'))['enter'])
            payload=json.loads(path.read_text());payload['model']['intercept']+=1;path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):RidgeModel.load(path)

    def test_costs_compare_log_to_log(self):
        m=RidgeModel('BTCUSDT',1,[0]*6,[1]*6,[0]*6,980,0,0,0,100,30,1,2)
        # 10% arithmetic cost is 953.1 log bps, not 1000 log bps.
        self.assertTrue(m.decision(np.zeros(6),dec('1000'),0)['enter'])
        self.assertFalse(m.decision(np.zeros(6),dec('1100'),0)['enter'])


if __name__=='__main__':unittest.main()
