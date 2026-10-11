"""Verify the first mark-price pilot and acquire the remainder of the fixed week."""
import argparse
from datetime import date,timedelta
import json
from pathlib import Path
from urllib.parse import urlencode
from download_usdm_marks import download,parse_page
from download_usdm_funding import timestamp
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json


def audit_marks(root,day):
    root=Path(root)
    summary=root/'summary.json'
    hashes={str(summary.resolve()):sha256(summary)}
    m=json.loads(summary.read_text())
    start=timestamp(day);stop=start+86400000
    expected=dict(venue='binance_usdm',kind='mark_price_1m',symbol='ETHUSDT',date=str(day),
                  rows=1440,first_open_ms=start,last_open_ms=stop-60000)
    if any(m.get(k)!=v for k,v in expected.items()) or m.get('approved') is not False:
        raise ValueError('Mark identity/range mismatch')
    reserve=date.fromisoformat(m['reserve_from'])
    if not day<reserve<=date(2026,9,1):
        raise ValueError('Mark reserve mismatch')
    pages=m['pages']
    if not isinstance(pages,list) or not 1<=len(pages)<=4:
        raise ValueError('Invalid mark page manifest')
    cursor=start;rows=[]
    for n,item in enumerate(pages):
        url='https://fapi.binance.com/fapi/v1/markPriceKlines?'+urlencode(dict(symbol='ETHUSDT',interval='1m',startTime=cursor,endTime=stop-1,limit=1000))
        name=f'page-{n:02d}.json'
        if cursor>=stop or item.get('file')!=name or item.get('url')!=url:
            raise ValueError('Invalid mark pagination')
        path=root/name
        h=sha256(path)
        if h!=item['sha256'] or path.stat().st_size>1024**2:
            raise ValueError('Mark page integrity mismatch')
        hashes[str(path.resolve())]=h
        page=parse_page(json.loads(path.read_text()),cursor,stop)
        if not page or len(page)!=item['rows']:
            raise ValueError('Mark page count mismatch')
        rows.extend(page);cursor=page[-1]['open_ms']+60000
    normalized=root/'marks.json'
    h=sha256(normalized);hashes[str(normalized.resolve())]=h
    if cursor!=stop or len(rows)!=1440 or h!=m['marks_sha256'] or json.loads(normalized.read_text())!=rows:
        raise ValueError('Mark conversion or coverage mismatch')
    if any(sha256(p)!=h for p,h in hashes.items()):
        raise ValueError('Mark inputs changed during audit')
    return dict(approved=False,date=str(day),integrity_passed=True,raw_conversion_equal=True,
                rows=1440,inputs_sha256=hashes)


def run(first,output):
    first=Path(first);output=Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Output exists; choose a new path')
    start=date(2026,8,1)
    first_report=audit_marks(first,start)
    output.mkdir(parents=True,exist_ok=False)
    status=dict(approved=False,status='running',symbol='ETHUSDT',start=str(start),end_exclusive='2026-08-08',
                completed_days=[],active_day=None,runner_sha256=sha256(Path(__file__)))
    try:
        for i in range(7):
            day=start+timedelta(days=i)
            status['active_day']=str(day);atomic_json(output/'status.json',status)
            print(f'[mark-batch] day {i+1}/7: {day}',flush=True)
            if i==0:
                report=first_report
            else:
                download('ETHUSDT',day,date(2026,9,1),output/str(day))
                report=audit_marks(output/str(day),day)
            path=output/f'{day}-audit.json';atomic_json(path,report)
            status['completed_days'].append(dict(date=str(day),audit=path.name,sha256=sha256(path)))
            atomic_json(output/'status.json',status)
        for item in status['completed_days']:
            path=output/item['audit']
            if sha256(path)!=item['sha256']:
                raise ValueError('Saved mark audit changed')
            for source,digest in json.loads(path.read_text())['inputs_sha256'].items():
                if sha256(source)!=digest:
                    raise ValueError('Audited mark input changed')
        status.update(status='complete',active_day=None,days=7,minutes=10080)
        atomic_json(output/'status.json',status)
    except BaseException as error:
        status.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',error_type=type(error).__name__)
        try:
            atomic_json(output/'status.json',status)
        except Exception as save_error:
            error.add_note(f'Failed to save status: {type(save_error).__name__}')
        raise
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--first-pilot',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.first_pilot,a.output_dir),indent=2))


if __name__=='__main__':
    main()
