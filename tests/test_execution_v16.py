import unittest
import tempfile
import csv
import json
from pathlib import Path
from unittest.mock import patch
from engine_v1.dataset import sha256
from backtest_v16 import main
from decimal import Decimal
from dataclasses import replace
from backtest_v16 import Costs, simulate, MINUTE
from engine_v1.model import RidgeModel


def model(intercept=100):
    return RidgeModel('BTCUSDT',3,[0]*6,[1]*6,[0]*6,intercept,0,0,0,100,30,1,1)


def rows(n=60):
    return [dict(timestamp=i*MINUTE,open='100',close='100',high='100',low='100',volume='1') for i in range(n)]


class ExecutionTests(unittest.TestCase):
    def test_flat_market_charges_both_sides_and_reconciles(self):
        report=simulate(rows(),model(),21*MINUTE,60*MINUTE)
        s=report['summary']
        self.assertGreater(s['closed_trades'],0)
        self.assertLess(Decimal(s['net_pnl']),0)
        self.assertGreater(Decimal(s['fees']),0)
        self.assertGreater(s['max_drawdown_pct'],0)
        self.assertEqual(sum(Decimal(t['net_pnl']) for t in report['trades']),Decimal(s['net_pnl']))
        for t in report['trades']:
            self.assertEqual(t['entry_ms']-t['decision_ms'],MINUTE)
            self.assertEqual(t['exit_ms']-t['entry_ms'],3*MINUTE)
        for a,b in zip(report['trades'],report['trades'][1:]):
            self.assertGreaterEqual(b['entry_ms'],a['exit_ms'])

    def test_zero_signal_keeps_cash(self):
        report=simulate(rows(),model(0),21*MINUTE,60*MINUTE)
        self.assertEqual(report['summary']['closed_trades'],0)
        self.assertEqual(Decimal(report['summary']['net_pnl']),0)
        self.assertIsNone(report['summary']['win_rate_pct'])

    def test_zero_cost_constant_prices(self):
        c=Costs(fee_bps=0,spread_bps=0,slippage_bps=0)
        result=simulate(rows(),model(),21*MINUTE,60*MINUTE,c)
        self.assertEqual(Decimal(result['summary']['net_pnl']),0)

    def test_gap_and_truncated_interval_fail(self):
        for data in (rows()[:30]+rows()[31:],rows()[:-1]):
            with self.assertRaises(ValueError):
                simulate(data,model(),21*MINUTE,60*MINUTE)

    def test_cost_validation(self):
        for c in (Costs(fee_bps=-1),Costs(delay_bars=-1),Costs(qty_step='NaN'),Costs(capital=0)):
            with self.assertRaises(ValueError):
                simulate(rows(),model(),21*MINUTE,60*MINUTE,c)

    def test_past_calibration_required(self):
        m=replace(model(),calibration_end_ms=22*MINUTE)
        with self.assertRaises(ValueError):
            simulate(rows(),m,21*MINUTE,60*MINUTE)

    def test_future_close_cannot_change_first_entry(self):
        data=rows()
        m=model(0)
        m.coef[0]=100000
        # The close at minute 21 only becomes visible at minute 22.
        data[21]=dict(data[21],close='110',high='110')
        result=simulate(data,m,21*MINUTE,60*MINUTE,Costs(delay_bars=0))
        self.assertEqual(result['trades'][0]['decision_ms'],22*MINUTE)
        self.assertEqual(result['trades'][0]['entry_ms'],22*MINUTE)

    def test_delayed_price_changes_actual_fill(self):
        data=rows()
        data[22]=dict(data[22],open='110',high='110')
        result=simulate(data,model(),21*MINUTE,60*MINUTE)
        self.assertEqual(Decimal(result['trades'][0]['entry_price']),Decimal('110.033'))

    def test_rounded_minimum_prevents_trade(self):
        result=simulate(rows(),model(),21*MINUTE,60*MINUTE,Costs(qty_step='100'))
        self.assertEqual(result['summary']['closed_trades'],0)
        self.assertGreater(result['summary']['unfilled_candidates'],0)

    def test_cli_report_and_provenance_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            path=root/'candles.csv'
            with path.open('w') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows()[0]))
                writer.writeheader()
                for row in rows(1440):
                    writer.writerow(dict(row,timestamp=row['timestamp']//1000))
            sidecar=path.with_suffix('.json')
            meta=dict(sha256=sha256(path),venue='binance',symbol='BTCUSDT',timeframe_ms=MINUTE)
            sidecar.write_text(json.dumps(meta))
            artifact=root/'model.json'
            model(0).save(artifact)
            output=root/'result.json'
            args=['backtest_v16.py','--files',str(path),'--model',str(artifact),
                  '--start','1970-01-01','--end','1970-01-02','--output',str(output)]
            with patch('sys.argv',args),patch('sys.stdout'),patch('sys.stderr'):
                self.assertEqual(main(),0)
                original=output.read_bytes()
                self.assertEqual(main(),2)
                self.assertEqual(output.read_bytes(),original)
                self.assertFalse(json.loads(original)['approved'])
                output.unlink()
                meta['symbol']='ETHUSDT'
                sidecar.write_text(json.dumps(meta))
                self.assertEqual(main(),2)
                self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
