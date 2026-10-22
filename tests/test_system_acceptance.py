from pathlib import Path
import tempfile
import unittest
from run_system_acceptance import ledger_lifecycle, assess_feed


class AcceptanceTests(unittest.TestCase):
    def test_complete_isolated_ledger_lifecycle_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'control'
            result=ledger_lifecycle(root)
            self.assertTrue(result['passed'])
            self.assertEqual(result['trade_events'],4)
            with self.assertRaises(FileExistsError):ledger_lifecycle(root)

    def test_connected_but_unhealthy_does_not_pass(self):
        raw=dict(observe_only=True,duration_seconds=1801,messages=100,clock_ok=True,errors={})
        health=dict(observe_only=True,running=False,connection_state='stopped',clock_ok=True,errors={},
                    warm_candles={'BTCUSDT':21,'ETHUSDT':21},quote_age_ms={'BTCUSDT':10,'ETHUSDT':10})
        self.assertTrue(assess_feed(raw,health,1800,{'BTCUSDT','ETHUSDT'})['passed'])
        health['quote_age_ms']['ETHUSDT']=1001
        self.assertFalse(assess_feed(raw,health,1800,{'BTCUSDT','ETHUSDT'})['passed'])
        health['quote_age_ms']['ETHUSDT']=10
        raw['duration_seconds']=60
        self.assertFalse(assess_feed(raw,health,1800,{'BTCUSDT','ETHUSDT'})['passed'])
        raw['duration_seconds']=1801;raw['errors']={'TimeoutError':1}
        self.assertFalse(assess_feed(raw,health,1800,{'BTCUSDT','ETHUSDT'})['passed'])
