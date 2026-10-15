"""Bounded JSONL writer with byte-budgeted free-space probes."""
import hashlib
import json
import shutil

from record_market import Writer, StorageLimit


class QuoteWriter(Writer):
    probe_bytes = 1024 * 1024

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.free_at_probe = None
        self.bytes_at_probe = 0

    def write(self, record):
        payload = (json.dumps(record, separators=(',', ':'), allow_nan=False)+'\n').encode()
        if self.total + len(payload) > self.limit:
            raise StorageLimit('byte_budget')
        since_probe = self.total - self.bytes_at_probe
        if (self.free_at_probe is None or since_probe + len(payload) >= self.probe_bytes
                or self.free_at_probe - since_probe - len(payload) < self.reserve):
            self.free_at_probe = shutil.disk_usage(self.root).free
            self.bytes_at_probe = self.total
            since_probe = 0
        if self.free_at_probe - since_probe - len(payload) < self.reserve:
            raise StorageLimit('disk_reserve')
        if self.handle and self.size + len(payload) > self.chunk:
            self.close_part()
        if self.handle is None:
            self.path = self.root / f'events-{len(self.parts):05d}.jsonl'
            self.handle = self.path.open('xb')
            self.size = 0
            self.digest = hashlib.sha256()
        self.handle.write(payload)
        self.digest.update(payload)
        self.total += len(payload)
        self.size += len(payload)
