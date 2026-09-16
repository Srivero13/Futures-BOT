import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from engine_v1.progress import ProgressReporter
from engine_v1.stream import stream


class ProgressTests(unittest.TestCase):
    def args(self):
        return dict(state='connected',observe=True,elapsed=10,duration=60,messages=100,
                    reconnects=0,errors=0,fresh=2,symbols=2,warm=0,clock_ok=True)

    def test_throttle_and_force(self):
        output=io.StringIO(); clock=Mock(return_value=0)
        reporter=ProgressReporter(5,output,clock)
        reporter.update(**self.args())
        clock.return_value=4;reporter.update(**self.args())
        self.assertEqual(len(output.getvalue().splitlines()),1)
        clock.return_value=5;reporter.update(**self.args())
        reporter.update(**{**self.args(),'state':'stopped'},force=True)
        self.assertEqual(len(output.getvalue().splitlines()),3)
        self.assertIn('remaining=50s',output.getvalue())

    def test_quiet_disables_even_forced_events(self):
        output=io.StringIO();ProgressReporter(0,output).update(**self.args(),force=True)
        self.assertEqual(output.getvalue(),'')

    def test_bad_intervals(self):
        for value in (-1,.5,float('nan'),float('inf')):
            with self.assertRaises(ValueError):ProgressReporter(value)

    def test_broken_output_is_disabled_without_raising(self):
        output=Mock();output.write.side_effect=BrokenPipeError()
        reporter=ProgressReporter(5,output)
        reporter.update(**self.args(),force=True)
        self.assertTrue(reporter.disabled)
        output.reset_mock();reporter.update(**self.args(),force=True)
        output.write.assert_not_called()

    def test_continuous_zero_elapsed_and_retries(self):
        output=io.StringIO()
        ProgressReporter(5,output).update(**{**self.args(),'duration':0,'elapsed':0,'state':'retrying','fresh':0})
        self.assertIn('remaining=unlimited',output.getvalue())
        self.assertIn('fresh_quotes=0/2',output.getvalue())
        self.assertIn('retrying',output.getvalue())

    def test_observer_progress_stays_on_stderr_and_counts_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=Path(tmp)/'config.json'
            cfg.write_text(json.dumps({'mode':'paper','accounts':[{'id':'a','symbol':'BTCUSDT'}],
                'model_directory':'missing','database':str(Path(tmp)/'unused.db')}))
            sock=Mock()
            sock.recv.side_effect=[json.dumps({'s':'BTCUSDT','u':1,'b':'100','a':'101','B':'2','A':'2'}),KeyboardInterrupt]
            stderr=io.StringIO();stdout=io.StringIO()
            with patch('engine_v1.stream.websocket.create_connection',return_value=sock),patch('sys.stderr',stderr),patch('sys.stdout',stdout):
                result=stream(10,config_path=cfg,health_path=Path(tmp)/'health.json')
            self.assertEqual(result['messages'],1)
            self.assertEqual(stdout.getvalue(),'')
            self.assertIn('connected',stderr.getvalue())
            self.assertIn('stopped',stderr.getvalue())
            self.assertIn('messages=1 ',stderr.getvalue())
            self.assertEqual(json.loads((Path(tmp)/'health.json').read_text())['connection_state'],'stopped')
            sock.close.assert_called_once()
