import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from basis_quote_writer import QuoteWriter
from record_market import StorageLimit


class QuoteWriterTests(unittest.TestCase):
    def test_burst_preserves_records_hashes_rotation_and_bounds_probe_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = QuoteWriter(tmp, 4*1024**2, chunk=128*1024)
            record = {'payload': 'x'*300}
            with patch('basis_quote_writer.shutil.disk_usage', return_value=SimpleNamespace(free=10*1024**3)) as probe:
                for _ in range(10000):
                    writer.write(record)
                writer.close_part()
                self.assertLessEqual(probe.call_count, 4)
            count = 0
            for part in writer.parts:
                data = (Path(tmp)/part['file']).read_bytes()
                self.assertEqual(len(data), part['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), part['sha256'])
                for line in data.splitlines():
                    self.assertEqual(json.loads(line), record)
                    count += 1
            self.assertEqual(count, 10000)

    def test_byte_budget_and_reserve_fail_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = QuoteWriter(tmp, 1)
            with self.assertRaisesRegex(StorageLimit, 'byte_budget'):
                writer.write({'x': 1})
            writer = QuoteWriter(tmp, 1000, reserve=100)
            with patch('basis_quote_writer.shutil.disk_usage', return_value=SimpleNamespace(free=100)):
                with self.assertRaisesRegex(StorageLimit, 'disk_reserve'):
                    writer.write({'x': 1})
            self.assertEqual(writer.total, 0)

    def test_external_space_loss_detected_at_next_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = QuoteWriter(tmp, 10000, reserve=100)
            writer.probe_bytes = 100
            with patch('basis_quote_writer.shutil.disk_usage', side_effect=[SimpleNamespace(free=10000), SimpleNamespace(free=100)]):
                writer.write({'x': 'a'*70})
                with self.assertRaisesRegex(StorageLimit, 'disk_reserve'):
                    writer.write({'x': 'b'*70})
            writer.close_part()
            self.assertEqual(len(writer.parts), 1)
