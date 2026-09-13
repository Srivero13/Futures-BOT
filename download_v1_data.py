"""Download official Binance monthly archives and verify published SHA256."""
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from urllib.request import urlopen
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parent

def fetch(url):
    with urlopen(url, timeout=30) as r:
        return r.read()

def main():
    dest = ROOT / 'datasets'
    dest.mkdir(exist_ok=True)
    manifest = {'source': 'Binance public data', 'retrieved_utc': datetime.now(timezone.utc).isoformat(), 'archives': []}
    for symbol in ('BTCUSDT', 'ETHUSDT'):
        rows = []
        for month in ('2025-04', '2025-05', '2025-06'):
            name = f'{symbol}-1m-{month}.zip'
            url = f'https://data.binance.vision/data/spot/monthly/klines/{symbol}/1m/{name}'
            blob = fetch(url)
            expected = fetch(url + '.CHECKSUM').decode().split()[0]
            actual = hashlib.sha256(blob).hexdigest()
            if expected != actual:
                raise ValueError('Checksum mismatch: ' + name)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                content = z.read(name.replace('.zip', '.csv')).decode()
            for r in csv.reader(io.StringIO(content)):
                stamp = int(r[0])
                stamp //= 1000000 if stamp > 10**14 else 1000
                rows.append([stamp, *r[1:6]])
            manifest['archives'].append({'url': url, 'sha256': actual})
            print(name, 'checksum OK', flush=True)
        path = dest / f'{symbol}-1m-2025Q2.csv'
        with path.open('w', newline='') as f:
            w = csv.writer(f); w.writerow(['timestamp','open','high','low','close','volume']); w.writerows(rows)
        manifest[symbol] = {'rows': len(rows), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (dest/'manifest-v1.json').write_text(json.dumps(manifest, indent=2)+'\n')
if __name__ == '__main__':
    main()
