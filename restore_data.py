"""Restore bundled public research CSVs after verifying their SHA256 hashes."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile
ROOT = Path(__file__).resolve().parent

def main():
    folder = ROOT / 'data_bundle'
    manifest = json.loads((folder / 'manifest.json').read_text())
    chunks = []
    for part in manifest['parts']:
        blob = base64.b64decode((folder / part['name']).read_bytes(), validate=True)
        if hashlib.sha256(blob).hexdigest() != part['sha256']:
            raise ValueError('Part checksum mismatch: ' + part['name'])
        chunks.append(blob)
    archive = b''.join(chunks)
    if hashlib.sha256(archive).hexdigest() != manifest['archive_sha256']:
        raise ValueError('Archive checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if set(z.namelist()) != set(manifest['files']):
            raise ValueError('Archive file list mismatch')
        # Validate every path and content before writing anything.
        verified = []
        for name, expected in manifest['files'].items():
            path = (ROOT / name).resolve()
            if ROOT not in path.parents:
                raise ValueError('Unsafe archive path')
            blob = z.read(name)
            if hashlib.sha256(blob).hexdigest() != expected:
                raise ValueError('File checksum mismatch: ' + name)
            if path.exists() and path.read_bytes() != blob:
                raise ValueError('Local file differs; move it before restoring: ' + name)
            verified.append((path, blob))
        for path, blob in verified:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
    print(f'{len(verified)} CSV files restored and verified.')

if __name__ == '__main__':
    main()
