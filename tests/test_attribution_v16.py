import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from decimal import Decimal as D
from attribute_v16 import attribute_trade,summarize,run
from backtest_v16 import Costs,simulate
from dataclasses import asdict
from reversal_v16 import ResearchSpec
from engine_v1.dataset import sha256


def fixture_trade():
    qty=D('1');buy=D('110')*D('1.0003');sell=D('120')*D('.9997')
    fees=(buy+sell)*D('.001');impact=(buy-110)+(120-sell)
    return dict(decision_ms=0,entry_ms=60000,exit_ms=960000,quantity='1',entry_price=str(buy),exit_price=str(sell),fees=str(fees),spread_slippage_cost=str(impact),net_pnl=str(sell-buy-fees))


class AttributionTests(unittest.TestCase):
    def test_exact_decomposition(self):
        r=attribute_trade(fixture_trade(),{0:100,60000:110,960000:120},asdict(Costs()))
        self.assertEqual(D(r['delay_price_change_same_quantity']),10)
        self.assertEqual(D(r['holding_gross_pnl']),10)
        self.assertEqual(D(r['holding_gross_pnl'])-D(r['fees'])-D(r['spread_slippage_cost']),D(r['net_pnl']))
        self.assertAlmostEqual(r['delay_log_bps']+r['holding_log_bps'],r['signal_to_exit_log_bps'])

    def test_tampered_fill_fails(self):
        for key in ('entry_price','exit_price','fees','spread_slippage_cost','net_pnl'):
            t=fixture_trade();t[key]=str(D(t[key])+1)
            with self.assertRaisesRegex(ValueError,'reconcile'):
                attribute_trade(t,{0:100,60000:110,960000:120},asdict(Costs()))

    def test_empty_summary_and_invalid_times(self):
        self.assertEqual(summarize([])['net_pnl'],'0')
        self.assertIsNone(summarize([])['mean_delay_log_bps'])
        t=fixture_trade();t['entry_ms']=1
        with self.assertRaises(ValueError):attribute_trade(t,{},asdict(Costs()))

    def test_pipeline_checksums_counts_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);path=root/'data.csv'
            rows=[dict(timestamp=i*60000,open='100',close='100',high='100',low='100',volume='1') for i in range(180)]
            fold=simulate(rows,ResearchSpec(0),30*60000,180*60000,entry_rule=lambda x,ts:ts%900000==0)
            fold.update(test_start='1970-01-01',test_end='1970-01-02')
            with path.open('w') as f:
                w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader()
                for row in rows:w.writerow(dict(row,timestamp=row['timestamp']//1000))
            digest=sha256(path)
            path.with_suffix('.json').write_text(json.dumps(dict(sha256=digest,symbol='ETHUSDT',venue='binance',timeframe_ms=60000,last_open_ms=179*60000)))
            source={'protocol':{'sources':[{'sha256':digest}], 'symbol':'ETHUSDT','reserve_from':'1970-02-01','costs':asdict(Costs()),'horizon_minutes':15},
                    'folds':[fold],'summary':{'closed_trades':len(fold['trades']),'sum_independent_month_net_pnl':fold['summary']['net_pnl']}}
            report=root/'source.json';report.write_text(json.dumps(source));output=root/'out.json'
            with patch('sys.stdout'):
                result=run(report,[path],output)
                self.assertFalse(result['approved'])
                self.assertEqual(D(result['summary']['net_pnl']),D(fold['summary']['net_pnl']))
                with self.assertRaises(ValueError):run(report,[path],output)
                output.unlink()
                source['summary']['closed_trades']+=1;report.write_text(json.dumps(source))
                with self.assertRaisesRegex(ValueError,'Aggregate'):run(report,[path],output)
                self.assertFalse(output.exists())
                path.write_text('changed')
                with self.assertRaisesRegex(ValueError,'checksum'):run(report,[path],output)


if __name__=='__main__':unittest.main()
