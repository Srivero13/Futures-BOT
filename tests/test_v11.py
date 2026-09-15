import json
from decimal import localcontext
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from engine_v1.core import Portfolio,Quote,dec
from engine_v1.latency import policy
from engine_v1.model import RidgeModel,feature_matrix,fit_model
from engine_v1.operations import atomic_json,backup_database,process_lock,read_status
from engine_v1.stream import FeedState,entry_gate,load_profile,rules_from_exchange,stream
from train_v11 import block_interval,promote
from test_v1 import accounts,quote
import test_v1 as fixtures


class EngineV11Tests(unittest.TestCase):
    def test_precision_is_independent_of_callers(self):
        results=[]
        for precision in (6,28,50):
            with localcontext() as ctx:
                ctx.prec=precision
                p=Portfolio(':memory:',accounts(),slip_bps='0')
                try:
                    p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='buy')
                    p.process({'BTCUSDT':quote('101',2,61000)},{'0':{'exit':True}},61000,event_id='sell')
                    results.append(p.states()[0]['cash'])
                    self.assertEqual(ctx.prec,precision)
                finally:p.close()
        self.assertEqual(len(set(results)),1);self.assertEqual(dec(results[0]),dec('1000.799'))

    def test_stale_btc_does_not_block_eth_exit(self):
        acc=accounts(2);acc[1]['symbol']='ETHUSDT';p=Portfolio(':memory:',acc,slip_bps='0',fee_bps='0')
        try:
            p.process({'BTCUSDT':quote(),'ETHUSDT':quote(symbol='ETHUSDT')},{'0':{'enter':True},'1':{'enter':True}},1000,event_id='buy')
            events=p.process({'BTCUSDT':quote(),'ETHUSDT':quote(symbol='ETHUSDT',seq=2,ts=3000)},{'1':{'exit':True}},3000,event_id='exit')
            self.assertEqual(events[0]['action'],'STALE_PORTFOLIO')
            self.assertEqual(events[1]['action'],'SELL')
            self.assertGreater(dec(p.states()[0]['qty']),0);self.assertEqual(dec(p.states()[1]['qty']),0)
        finally:p.close()

    def test_pause_preserves_exits_and_flatten_blocks_entries(self):
        p=Portfolio(':memory:',accounts())
        try:
            e=p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='paused',allow_entries=False)
            self.assertEqual(e[0]['action'],'HOLD')
            p.process({'BTCUSDT':quote(seq=2)},{'0':{'enter':True}},1000,event_id='buy')
            e=p.process({'BTCUSDT':quote(seq=3)},{'0':{'enter':True}},1000,event_id='flatten',force_exit=True)
            self.assertEqual(e[0]['action'],'SELL')
            e=p.process({'BTCUSDT':quote(seq=4)},{'0':{'enter':True}},1000,event_id='flat',force_exit=True,cooldown_ms=0)
            self.assertEqual(e[0]['action'],'HOLD')
        finally:p.close()

    def test_idle_events_not_logged_and_old_replay_rejected_after_prune(self):
        p=Portfolio(':memory:',accounts())
        try:
            for i in range(10):p.process({'BTCUSDT':quote(ts=i*86400000,seq=i)},{},i*86400000,event_id=str(i))
            self.assertEqual(p.db.execute('SELECT count(*) FROM events').fetchone()[0],0)
            p.prune(9*86400000)
            self.assertEqual(p.db.execute('SELECT count(*) FROM processed').fetchone()[0],2)
            with self.assertRaises(ValueError):p.process({'BTCUSDT':quote(ts=0,seq=100)},{'0':{'enter':True}},0,event_id='old')
        finally:p.close()

    def test_refreshing_quote_deadline_preserves_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db';p=Portfolio(path,accounts(),max_age_ms=300);p.close()
            p=Portfolio(path,accounts(),max_age_ms=800);p.close()

    def test_invalid_quote_mapping_does_not_mutate(self):
        p=Portfolio(':memory:',accounts())
        try:
            with self.assertRaises(ValueError):p.process({'BTCUSDT':quote(symbol='ETHUSDT')},{},1000,event_id='bad')
            self.assertEqual(p.states()[0]['last_timestamp_ms'],-1)
        finally:p.close()

    def test_atomic_rollback_across_accounts(self):
        p=Portfolio(':memory:',accounts(2))
        try:
            p.process({'BTCUSDT':quote(seq=5)},{},1000,event_id='warm')
            before=p.states()
            with self.assertRaises(ValueError):p.process({'BTCUSDT':quote(seq=4)},{'0':{'enter':True},'1':{'enter':True}},1000,event_id='bad')
            self.assertEqual(before,p.states());self.assertFalse(p.db.execute('SELECT * FROM processed WHERE event="bad"').fetchall())
        finally:p.close()


class OperationsTests(unittest.TestCase):
    def test_second_coordinator_cannot_take_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'lock'
            with process_lock(path):
                with self.assertRaises(RuntimeError):
                    with process_lock(path):pass
            with process_lock(path):pass

    def test_backup_captures_wal_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'src.sqlite3';dst=Path(tmp)/'dst.sqlite3';p=Portfolio(src,accounts())
            try:
                p.process({'BTCUSDT':quote()},{'0':{'enter':True}},1000,event_id='buy')
                backup_database(src,dst)
                db=sqlite3.connect(dst)
                try:self.assertEqual(json.loads(db.execute('SELECT state FROM accounts').fetchone()[0]),p.states()[0])
                finally:db.close()
                with self.assertRaises(ValueError):backup_database(src,dst)
            finally:p.close()

    def test_atomic_health_and_expiration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'health.json';atomic_json(path,{'timestamp_ms':1000,'running':True})
            with patch('engine_v1.operations.time.time',return_value=2):self.assertTrue(read_status(path)['heartbeat_current'])
            with patch('engine_v1.operations.time.time',return_value=20):self.assertFalse(read_status(path)['heartbeat_current'])
            with self.assertRaises(ValueError):atomic_json(path,{'bad':float('nan')})
            self.assertEqual(json.loads(path.read_text())['timestamp_ms'],1000)

    def test_profile_recomputes_eligibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profile.json'
            p={'created_at_ms':1000,'location':'user-pc','clock_estimate':{'offset_ms':0,'uncertainty_ms':50},'endpoints':{}}
            for label in ('quote','server_time'):p['endpoints'][label]={'eligible_for_paper_stream':True,'quote_deadline_ms':99999,'samples':[{'ok':True,'rtt_ms':100} for _ in range(30)]}
            path.write_text(json.dumps(p));self.assertEqual(load_profile(path,1001)['endpoints']['quote']['quote_deadline_ms'],300)
            p['endpoints']['quote']['samples'][0]['rtt_ms']=2000;path.write_text(json.dumps(p))
            with self.assertRaises(ValueError):load_profile(path,1001)

    def test_profile_rejects_nan_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            p={'created_at_ms':1000,'location':'user-pc','clock_estimate':{'offset_ms':float('nan'),'uncertainty_ms':50},'endpoints':{label:{'samples':[{'ok':True,'rtt_ms':100} for _ in range(30)]} for label in ('quote','server_time')}}
            path=Path(tmp)/'p';path.write_text(json.dumps(p))
            with self.assertRaises(ValueError):load_profile(path,1001)

    def test_latency_rejects_inconsistent_counts(self):
        for samples,failures,attempts in [([1],0,2),([float('nan')],0,1),([-1],0,1)]:
            with self.assertRaises(ValueError):policy(samples,failures,attempts)

    def test_halted_symbol_rejected(self):
        with self.assertRaises(ValueError):rules_from_exchange({'status':'BREAK','filters':[]})

    def test_invalid_candle_does_not_advance_feed(self):
        f=FeedState()
        with self.assertRaises(ValueError):f.accept_kline({'s':'BTCUSDT','k':{'t':60000,'x':True,'o':'100','h':'99','l':'90','c':'100','v':'1'}})
        self.assertFalse(f.last_closed)

    def test_observer_does_not_need_model_files(self):
        # A controlled disconnect verifies shutdown without any public network request.
        with tempfile.TemporaryDirectory() as tmp:
            cfg={'mode':'paper','database':str(Path(tmp)/'db'),'model_directory':'missing','accounts':accounts()}
            path=Path(tmp)/'config.json';path.write_text(json.dumps(cfg))
            with patch('engine_v1.stream.websocket.create_connection',side_effect=KeyboardInterrupt):
                result=stream(1,observe=True,config_path=path,health_path=Path(tmp)/'health.json')
            self.assertEqual(result['messages'],0);self.assertFalse((Path(tmp)/'db').exists())
            self.assertFalse(json.loads((Path(tmp)/'health.json').read_text())['running'])


class ModelV11Tests(unittest.TestCase):
    def test_scaled_model_holdout_invariance(self):
        rows=fixtures.ModelTests.rows();x=feature_matrix(rows)
        m=fit_model(rows,x,'BTCUSDT',3,300,400,volatility_scaled=True)
        changed=rows[:400]+[{**r,'open':'10000','close':'10000','high':'10001'} for r in rows[400:]]
        self.assertEqual(m,fit_model(changed,feature_matrix(changed),'BTCUSDT',3,300,400,volatility_scaled=True))
        self.assertGreater(m.volatility_floor,0);self.assertTrue(np.isfinite(m.predict(x[100])))

    def test_scaled_model_roundtrip(self):
        rows=fixtures.ModelTests.rows();x=feature_matrix(rows);m=fit_model(rows,x,'BTCUSDT',3,300,400,volatility_scaled=True)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model';m.save(path);other=RidgeModel.load(path)
            self.assertEqual(m.decision(x[100],dec('20')),other.decision(x[100],dec('20')))

    def test_shape_and_cost_validation(self):
        rows=fixtures.ModelTests.rows();m=fit_model(rows,feature_matrix(rows),'BTCUSDT',1,300,400)
        self.assertIsNone(m.predict([1,2]));self.assertFalse(m.decision(np.zeros(6),float('nan'))['enter'])

    def test_bootstrap_deterministic_and_constant(self):
        self.assertEqual(block_interval([1]*14)['lower'],1)
        self.assertEqual(block_interval(range(14)),block_interval(range(14)))
        self.assertIsNone(block_interval([1]*3))

    def test_zero_trades_cannot_be_promoted(self):
        rows=fixtures.ModelTests.rows();m=fit_model(rows,feature_matrix(rows),'BTCUSDT',1,300,400)
        approved,_=promote(m,{'daily_pnl':['0']*14,'closed_trades':0,'net_pnl':'0'})
        self.assertFalse(approved)

    def test_gate_explains_expired_profile_and_pause(self):
        rows=fixtures.ModelTests.rows();m=fit_model(rows,feature_matrix(rows),'BTCUSDT',1,300,400)
        p={'created_at_ms':0,'endpoints':{'quote':{'minimum_horizon_ms':60000}}}
        self.assertEqual(entry_gate(m,FeedState(),'BTCUSDT',86400001,p),'profile_expired')
        self.assertEqual(entry_gate(m,FeedState(),'BTCUSDT',1,p,paused=True),'operator_paused')
        self.assertEqual(entry_gate(m,FeedState(),'BTCUSDT',1,p,clock_ok=False),'clock_jump')

if __name__=='__main__':unittest.main()
