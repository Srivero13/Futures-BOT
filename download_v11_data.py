"""Download Q2/Q3 2025 official spot candles with checksums and atomic output."""
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import zipfile
from download_data import fetch
ROOT=Path(__file__).resolve().parent


def main():
    dest=ROOT/'datasets';dest.mkdir(exist_ok=True)
    manifest={'source':'Binance public spot archives','retrieved_utc':datetime.now(timezone.utc).isoformat(),'archives':[]}
    for symbol in ('BTCUSDT','ETHUSDT'):
        rows=[]
        for month in ('2025-04','2025-05','2025-06','2025-07','2025-08','2025-09'):
            name=f'{symbol}-1m-{month}.zip'
            url=f'https://data.binance.vision/data/spot/monthly/klines/{symbol}/1m/{name}'
            blob=fetch(url);expected=fetch(url+'.CHECKSUM').decode().split()[0]
            digest=hashlib.sha256(blob).hexdigest()
            if digest!=expected:raise ValueError('Checksum mismatch: '+name)
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                content=archive.read(name.replace('.zip','.csv')).decode()
            for row in csv.reader(io.StringIO(content)):
                ts=int(row[0]);ts=ts//1000000 if ts>10**14 else ts//1000
                rows.append([ts,*row[1:6]])
            manifest['archives'].append({'url':url,'sha256':digest})
            print(name,'verified',flush=True)
        path=dest/f'{symbol}-1m-2025Q2Q3.csv';tmp=path.with_suffix('.tmp')
        with tmp.open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['timestamp','open','high','low','close','volume']);writer.writerows(rows)
        # Validate continuity and prices before replacing a dataset.
        from train_v1 import load_rows
        load_rows(tmp);tmp.replace(path)
        manifest[symbol]={'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (dest/'manifest-v1.1.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
