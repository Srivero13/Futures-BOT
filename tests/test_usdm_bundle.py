from contextlib import ExitStack
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from collect_usdm_bundle import run
from engine_v1.dataset import sha256


class BundleTests(unittest.TestCase):
    def setup(self,root,fail_marks=False):
        spot=root/'spot';spot.mkdir()
        (spot/'binance-ETHUSDT-2026-08.csv').write_text('fixture')
        (spot/'binance-ETHUSDT-2026-08.json').write_text('{}')
        calls=[]
        def download(*args):
            folder=Path(args[-1]);folder.mkdir(parents=True)
            (folder/'source').write_text('ok');calls.append(str(folder))
        def audit(folder,*args):
            source=Path(folder)/'source'
            if source.read_text()!='ok': raise ValueError('Corrupt input')
            return dict(inputs_sha256={str(source):sha256(source)},integrity_passed=True,
                        raw_conversion_equal=True,archive_conversion_equal=True,timestamp_alignment_passed=True,
                        matched_minutes=1440,rows=1440,records=3)
        stack=ExitStack()
        for name in ('trades','marks','funding'):
            stack.enter_context(patch('collect_usdm_bundle.download_'+name,side_effect=download))
            stack.enter_context(patch('collect_usdm_bundle.audit_'+name,side_effect=audit))
        return spot,calls,stack

    def test_resume_reaudits_without_redownloading_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spot,calls,stack=self.setup(root)
            with stack:
                out=root/'out';args=(date(2026,8,8),date(2026,8,10),spot,out)
                self.assertEqual(run(*args)['minutes'],2880)
                self.assertEqual(len(calls),5)
                self.assertEqual(run(*args)['status'],'complete');self.assertEqual(len(calls),5)
                (out/'marks/2026-08-08/source').write_text('bad')
                with self.assertRaises(ValueError): run(*args)
                self.assertEqual(json.loads((out/'bundle.json').read_text())['status'],'failed')

    def test_failure_keeps_completed_download_for_resume(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spot,calls,stack=self.setup(root)
            with stack:
                args=(date(2026,8,8),date(2026,8,9),spot,root/'out')
                with patch('collect_usdm_bundle.download_marks',side_effect=OSError('offline')):
                    with self.assertRaises(OSError): run(*args)
                self.assertEqual(run(*args)['status'],'complete')
                self.assertEqual(len(calls),3)

    def test_reserve_and_changed_identity_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spot,calls,stack=self.setup(root)
            with stack:
                out=root/'out';run(date(2026,8,8),date(2026,8,9),spot,out)
                with self.assertRaises(ValueError): run(date(2026,8,8),date(2026,8,10),spot,out)
                with self.assertRaises(ValueError): run(date(2026,8,31),date(2026,9,2),spot,root/'bad')
                self.assertFalse((root/'bad').exists())

    def test_24_days_split_funding_into_bounded_chunks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);spot,calls,stack=self.setup(root)
            with stack:
                r=run(date(2026,8,8),date(2026,9,1),spot,root/'out')
                self.assertEqual(r['minutes'],34560)
                self.assertEqual(len(r['completed_days']),24)
                self.assertEqual(len(r['funding_chunks']),4)
                self.assertEqual(r['funding_chunks'][-1]['end_exclusive'],'2026-09-01')
                self.assertEqual(len(calls),52)
