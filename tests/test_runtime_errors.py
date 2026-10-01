import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from engine_v1.runtime_errors import LocalRuntimeError, local_operation
from engine_v1.stream import stream


class RuntimeErrorTests(unittest.TestCase):
    def test_local_failures_are_fatal_and_preserve_cause(self):
        for error in (OSError('disk full'), sqlite3.OperationalError('locked'),
                      ValueError('event time moved backwards')):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(LocalRuntimeError) as raised:
                    local_operation('Paper ledger transaction',Mock(side_effect=error))
                self.assertIs(raised.exception.__cause__,error)
                self.assertIn('not retried',str(raised.exception))

    def test_success_returns_original_result(self):
        result=object()
        operation=Mock(return_value=result)
        self.assertIs(local_operation('Write',operation,1,flag=True),result)
        operation.assert_called_once_with(1,flag=True)

    def test_health_write_failure_closes_socket_without_reconnect(self):
        sock=Mock()
        calls=0
        def write(*args,**kwargs):
            nonlocal calls
            calls+=1
            # Initial health and connecting health succeed; connected health fails.
            if calls==3: raise OSError('disk full')
        with tempfile.TemporaryDirectory() as tmp, patch(
                'engine_v1.stream.atomic_json',side_effect=write), patch(
                'engine_v1.stream.websocket.create_connection',return_value=sock) as connect:
            with self.assertRaises(LocalRuntimeError):
                stream(duration=60,observe=True,health_path=Path(tmp)/'health.json',
                       progress_interval=0)
            connect.assert_called_once()
            sock.close.assert_called_once()
            sock.recv.assert_not_called()

    def test_network_failure_still_reconnects(self):
        sock=Mock()
        sock.recv.side_effect=KeyboardInterrupt
        with tempfile.TemporaryDirectory() as tmp, patch(
                'engine_v1.stream.websocket.create_connection',
                side_effect=[OSError('network down'),sock]) as connect, patch(
                'engine_v1.stream.random.random',return_value=0):
            result=stream(duration=5,observe=True,health_path=Path(tmp)/'health.json',
                          progress_interval=0)
        self.assertEqual(connect.call_count,2)
        self.assertEqual(result['reconnects'],1)
        self.assertEqual(result['errors'],{'OSError':1})
        sock.close.assert_called_once()


    def test_paper_transaction_failure_closes_ledger_and_socket(self):
        sock=Mock()
        sock.recv.return_value=json.dumps(dict(s='ETHUSDT',u=1,b='100',a='101',B='2',A='2'))
        engine=Mock()
        engine.states.return_value=[]
        engine.process.side_effect=sqlite3.OperationalError('database unavailable')
        model=Mock(symbol='ETHUSDT',horizon_bars=3)
        policy=dict(quote_deadline_ms=1000,minimum_decision_spacing_ms=1)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=root/'config.json'
            config.write_text(json.dumps(dict(mode='paper',accounts=[
                dict(id='test',symbol='ETHUSDT',capital='1000')],
                model_directory=tmp,database=str(root/'paper.db'),risk={},
                cooldown_ms=1000,max_entries_day=12)))
            with patch('engine_v1.stream.load_profile',return_value={'endpoints':{'quote':policy}}), patch(
                    'engine_v1.stream.load_model',return_value=model), patch(
                    'engine_v1.stream.Portfolio',return_value=engine), patch(
                    'engine_v1.stream.fetch_rules',return_value={}), patch(
                    'engine_v1.stream.entry_gate',return_value='model_unapproved'), patch(
                    'engine_v1.stream.websocket.create_connection',return_value=sock) as connect:
                with self.assertRaises(LocalRuntimeError):
                    stream(duration=60,observe=False,profile_path='unused',config_path=config,
                           health_path=root/'health.json',progress_interval=0)
            connect.assert_called_once()
            engine.process.assert_called_once()
            engine.close.assert_called_once()
            sock.close.assert_called_once()
