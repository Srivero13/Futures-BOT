"""One-day public mark-price candles for research valuation, never order fills."""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode
from download_v15_data import fetch_file
from download_usdm_funding import timestamp
from engine_v1.dataset import sha256
from engine_v1.operations import process_lock


def parse_page(payload, cursor, stop):
    if not isinstance(payload,list) or len(payload)>1000:
        raise ValueError('Invalid mark-price response')
    rows=[]
    for row in payload:
        if not isinstance(row,list) or len(row)!=12:
            raise ValueError('Invalid mark-price row schema')
        t=cursor+len(rows)*60000
        if type(row[0]) is not int or row[0]!=t or t>=stop or row[6]!=t+59999:
            raise ValueError('Missing, unordered or invalid mark-price timestamp')
        values=[Decimal(str(x)) for x in row[1:5]]
        if not all(x.is_finite() and x>0 for x in values):
            raise ValueError('Invalid mark OHLC')
        o,h,l,c=values
        if not l<=min(o,c)<=max(o,c)<=h:
            raise ValueError('Invalid mark OHLC bounds')
        rows.append(dict(open_ms=t,open=str(o),high=str(h),low=str(l),close=str(c)))
    return rows


def download(symbol,day,reserve,output):
    if not re.fullmatch(r'[A-Z0-9]{3,24}',symbol) or day>=reserve or day>=datetime.now(timezone.utc).date():
        raise ValueError('Invalid symbol/date or reserve')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with process_lock(str(output)+'.lock'):
        if output.exists() or output.is_symlink():
            raise ValueError('Output exists; choose a new path')
        with tempfile.TemporaryDirectory(prefix='marks-',dir=output.parent) as temp:
            stage=Path(temp)/'publish';stage.mkdir()
            cursor=timestamp(day);stop=cursor+86400000
            rows=[];pages=[]
            for n in range(4):
                if cursor==stop:
                    break
                url='https://fapi.binance.com/fapi/v1/markPriceKlines?'+urlencode(dict(symbol=symbol,interval='1m',startTime=cursor,endTime=stop-1,limit=1000))
                path=stage/f'page-{n:02d}.json'
                print(f'[marks] page {n+1}/4 | validated_minutes={len(rows)}/1440',flush=True)
                fetch_file(url,path,limit=1024**2)
                page=parse_page(json.loads(path.read_text()),cursor,stop)
                if not page:
                    raise ValueError('Incomplete mark-price day')
                rows.extend(page);cursor=page[-1]['open_ms']+60000
                pages.append(dict(file=path.name,url=url,sha256=sha256(path),rows=len(page)))
            if cursor!=stop or len(rows)!=1440:
                raise ValueError('Mark-price day not complete within page budget')
            normalized=stage/'marks.json';normalized.write_text(json.dumps(rows,indent=2)+'\n')
            result=dict(approved=False,venue='binance_usdm',kind='mark_price_1m',symbol=symbol,date=str(day),
                        rows=len(rows),first_open_ms=rows[0]['open_ms'],last_open_ms=rows[-1]['open_ms'],
                        reserve_from=str(reserve),marks_sha256=sha256(normalized),pages=pages,
                        runner_sha256=sha256(Path(__file__)),retrieved_utc=datetime.now(timezone.utc).isoformat(),
                        limitations=['Mark OHLC is a valuation reference, not executable bid/ask or trade volume.',
                                     'Minute bars cannot reconstruct every intraminute equity or liquidation event.',
                                     'API responses have local hashes, not exchange archive checksums.',
                                     'No risk model, strategy evaluation or approval.'])
            (stage/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
            os.rename(stage,output)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol',default='ETHUSDT')
    p.add_argument('--date',type=date.fromisoformat,required=True)
    p.add_argument('--reserve-from',type=date.fromisoformat,default=date(2026,9,1))
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(download(a.symbol,a.date,a.reserve_from,a.output_dir),indent=2))


if __name__=='__main__':
    main()
