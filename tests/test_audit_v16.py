import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from audit_v16 import quality,feature_month,feature_audit,run
from engine_v1.dataset import sha256
from train_v15 import timestamp


class AuditTests(unittest.TestCase):
    def test_missing_boundaries_and_interior(self):
        start=timestamp('2026-03-01');end=timestamp('2026-04-01')
        rows=[dict(timestamp=start+i*60000,open='100',high='100',low='100',close='100',volume='1') for i in (1,2,4)]
        m=quality(rows,start,end)['monthly']['2026-03']
        self.assertEqual(m['missing_minutes'],31*1440-3)
        self.assertEqual(m['observed_minutes'],3)

    def test_anomalies_and_gap_reset(self):
        start=timestamp('2026-03-01');end=timestamp('2026-04-01')
        rows=[dict(timestamp=start+i*60000,open='100',high='100',low='100',close='100',volume='1') for i in range(21)]
        rows[-1].update(open='110',close='110',high='110',volume='100')
        rows.append(dict(rows[-1],timestamp=start+25*60000,open='200',close='200',volume='0'))
        m=quality(rows,start,end)['monthly']['2026-03']
        self.assertEqual(m['large_close_moves'],1)
        self.assertEqual(m['large_open_jumps'],1)
        self.assertEqual(m['volume_spikes'],1)
        self.assertEqual(m['zero_volume'],1)

    def test_associations_and_constant(self):
        x=np.arange(40,dtype=float)
        data=np.column_stack([x,-x,np.zeros(40),x,x,x,x])
        r=feature_month(data)['features']
        self.assertAlmostEqual(r['return_1']['spearman'],1)
        self.assertAlmostEqual(r['momentum_5']['spearman'],-1)
        self.assertIsNone(r['momentum_20']['spearman'])

    def test_grid_and_boundary(self):
        start=timestamp('2026-03-01')
        b=np.array([[start+i*60000,start+(i+15)*60000,*([i]*6),i] for i in range(60)],dtype=float)
        r=feature_audit(lambda:iter([b]),start,start+60*60000,15)
        self.assertEqual(r['2026-03']['examples'],3)

    def test_pipeline_integrity_and_reservation(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);path=root/'data.csv';start=timestamp('2026-03-01')
            with path.open('w') as f:
                w=csv.DictWriter(f,fieldnames=['timestamp','open','high','low','close','volume']);w.writeheader()
                for i in range(180):
                    w.writerow(dict(timestamp=start//1000+i*60,open=100,high=100,low=100,close=100,volume=1))
            meta=dict(sha256=sha256(path),venue='binance',symbol='ETHUSDT',timeframe_ms=60000,last_open_ms=start+179*60000)
            sidecar=path.with_suffix('.json');sidecar.write_text(json.dumps(meta))
            output=root/'report.json'
            with patch('sys.stdout'):
                r=run([path],'ETHUSDT','2026-03-01','2026-04-01','2026-09-01',output)
                self.assertFalse(r['approved'])
                self.assertEqual(r['summary']['observed_minutes'],180)
                with self.assertRaises(ValueError):
                    run([path],'ETHUSDT','2026-03-01','2026-04-01','2026-09-01',output)
                output.unlink();meta['last_open_ms']=timestamp('2026-09-01');sidecar.write_text(json.dumps(meta))
                with self.assertRaisesRegex(ValueError,'reserved'):
                    run([path],'ETHUSDT','2026-03-01','2026-04-01','2026-09-01',output)
                self.assertFalse(output.exists())


if __name__=='__main__':unittest.main()
