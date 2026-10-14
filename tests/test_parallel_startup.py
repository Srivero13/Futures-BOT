"""Startup failures must not initialize CUDA or launch research workers."""
import builtins
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import parallel_research


class ParallelStartupTests(unittest.TestCase):
    def test_invalid_startup_stops_before_torch_and_preserves_inputs(self):
        cases = ('existing_output', 'dangling_output', 'missing_last_audit',
                 'malformed_last_audit', 'nonfinite_audit', 'nonobject_audit',
                 'invalid_timeout')
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); audits = root/'audits'; audits.mkdir()
                for month in range(3, 9):
                    (audits/f'ETHUSDT-2026-{month:02d}-alignment.json').write_text('{}')
                output = root/'out'
                last = audits/'ETHUSDT-2026-08-alignment.json'
                if case == 'existing_output':
                    output.mkdir(); (output/'keep.txt').write_text('preserve')
                elif case == 'dangling_output': output.symlink_to(root/'missing')
                elif case == 'missing_last_audit': last.unlink()
                elif case == 'malformed_last_audit': last.write_text('{')
                elif case == 'nonfinite_audit': last.write_text('{"value": NaN}')
                elif case == 'nonobject_audit': last.write_text('[]')
                argv = ['parallel_research.py', '--audit-dir', str(audits), '--output-dir', str(output)]
                if case == 'invalid_timeout': argv += ['--worker-timeout-seconds', 'nan']
                before = {p.name:p.read_bytes() for p in audits.iterdir()}
                original_import = builtins.__import__
                def guarded(name, *args, **kwargs):
                    if name == 'torch': self.fail('Startup error reached Torch')
                    return original_import(name, *args, **kwargs)
                with patch('sys.argv', argv), patch('builtins.__import__', side_effect=guarded), patch(
                        'parallel_research.run_workers') as workers, patch(
                        'engine_v1.research_mlp.fit_predict') as train:
                    with self.assertRaises(ValueError): parallel_research.main()
                    workers.assert_not_called(); train.assert_not_called()
                self.assertEqual(before, {p.name:p.read_bytes() for p in audits.iterdir()})
                if case == 'existing_output':
                    self.assertEqual((output/'keep.txt').read_text(), 'preserve')
                elif case == 'dangling_output': self.assertTrue(output.is_symlink())
                else: self.assertFalse(output.exists())
