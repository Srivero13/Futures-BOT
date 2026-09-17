"""Bounded public Binance spot aggTrades acquisition and closed-minute flow summaries."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException, localcontext
import io
import json
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json, process_lock

GIB=1024**3
FIELDS=['timestamp','available_at_ms','agg_events','trade_id_span_count','taker_buy_qty','taker_sell_qty',
        'taker_buy_quote','taker_sell_quote','volume_imbalance','notional_imbalance','first_price','last_price']


def root_bytes(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())


def space(root,budget,extra=0):
    if root_bytes(root)+extra>budget:raise OSError('Trade-flow directory budget exceeded')
    if shutil.disk_usage(root).free< GIB+extra:raise OSError('Keep at least 1 GiB free disk reserve')


def fetch(url,path,root,budget,limit):
    for attempt in range(3):
        try:
            size=0;last=time.monotonic()
            with urlopen(Request(url,headers={'User-Agent':'Futures-BOT-tradeflow-research'}),timeout=15) as response,path.open('wb') as out:
                while block:=response.read(1024*1024):
                    size+=len(block)
                    if size>limit:raise ValueError('Download exceeds per-file size limit')
                    space(root,budget,len(block));out.write(block)
                    if time.monotonic()-last>=5:
                        print(f'[tradeflow] downloaded {size/1024**2:.1f} MiB: {path.name}',flush=True);last=time.monotonic()
            return
        except (HTTPError,URLError,TimeoutError,OSError) as error:
            path.unlink(missing_ok=True)
            if isinstance(error,HTTPError) and error.code not in (429,500,502,503,504):raise
            if isinstance(error,OSError) and not isinstance(error,(URLError,TimeoutError)):raise
            if attempt==2:raise
            delay=2**attempt
            if isinstance(error,HTTPError):
                retry=error.headers.get('Retry-After','')
                if retry.isdigit():delay=max(delay,min(30,int(retry)))
            time.sleep(delay)
        except BaseException:
            path.unlink(missing_ok=True);raise


def boolean(value):
    if value.lower() not in ('true','false'):raise ValueError('Invalid source boolean')
    return value.lower()=='true'


def convert(archive,output,day,root,budget,max_uncompressed=4*GIB):
    start=int(day.timestamp())*1000000;end=start+86400*1000000
    multiplier=1 if day.year>=2025 else 1000
    previous=None;count=minutes=id_gaps=0;first_ts=last_ts=None;max_gap=0
    bucket=None;active=None
    with localcontext() as ctx:
        ctx.prec=50
        with zipfile.ZipFile(archive) as z:
            members=z.infolist()
            if len(members)!=1 or not members[0].filename.endswith('.csv') or members[0].file_size>max_uncompressed:
                raise ValueError('Expected one CSV member within uncompressed size limit')
            with z.open(members[0]) as raw,io.TextIOWrapper(raw,encoding='utf-8-sig',newline='') as text,output.open('w',newline='') as out:
                writer=csv.DictWriter(out,fieldnames=FIELDS);writer.writeheader()
                def emit():
                    nonlocal minutes
                    if bucket is None:return
                    buy,sell=bucket['taker_buy_qty'],bucket['taker_sell_qty']
                    bq,sq=bucket['taker_buy_quote'],bucket['taker_sell_quote']
                    bucket['volume_imbalance']=(buy-sell)/(buy+sell)
                    bucket['notional_imbalance']=(bq-sq)/(bq+sq)
                    space(root,budget,8192);writer.writerow(bucket);minutes+=1
                for row in csv.reader(text):
                    if not row:raise ValueError('Empty aggregate-trade record')
                    if count==0 and row[0].lower() in ('agg_trade_id','aggregate tradeid'):
                        if len(row)!=8:raise ValueError('Invalid header length')
                        continue
                    if len(row)!=8:raise ValueError('Expected eight spot aggTrades columns')
                    aid,first,last,ts=int(row[0]),int(row[3]),int(row[4]),int(row[5])*multiplier
                    price,qty=Decimal(row[1]),Decimal(row[2]);buyer_maker=boolean(row[6]);boolean(row[7])
                    if min(aid,first,last)<0 or first>last or not start<=ts<end:
                        raise ValueError('Trade IDs or timestamp outside requested day')
                    if not price.is_finite() or not qty.is_finite() or min(price,qty)<=0:
                        raise ValueError('Invalid price/quantity')
                    if previous is not None:
                        if aid<=previous[0] or ts<previous[1]:
                            raise ValueError('Unordered/duplicate aggregate trades')
                        id_gaps+=max(0,aid-previous[0]-1)
                        max_gap=max(max_gap,ts-previous[1])
                    previous=(aid,ts,last)
                    first_ts=ts if first_ts is None else first_ts;last_ts=ts;count+=1
                    minute=ts//60000000*60
                    if minute!=active:
                        emit();active=minute
                        bucket={'timestamp':minute,'available_at_ms':(minute+60)*1000,'agg_events':0,'trade_id_span_count':0,
                            'taker_buy_qty':Decimal(0),'taker_sell_qty':Decimal(0),
                            'taker_buy_quote':Decimal(0),'taker_sell_quote':Decimal(0),
                            'first_price':str(price),'last_price':str(price)}
                    side='sell' if buyer_maker else 'buy'
                    bucket[f'taker_{side}_qty']+=qty;bucket[f'taker_{side}_quote']+=qty*price
                    bucket['agg_events']+=1;bucket['trade_id_span_count']+=last-first+1;bucket['last_price']=str(price)
                    if count%250000==0:print(f'[tradeflow] validated {count:,} events',flush=True)
                emit()
    if not count:raise ValueError('Empty archive')
    return {'agg_events':count,'observed_minutes':minutes,'empty_minutes':1440-minutes,
            'aggregate_id_gaps':id_gaps,'first_trade_us':first_ts,'last_trade_us':last_ts,
            'max_intertrade_gap_us':max_gap,'source_timestamp_unit':'us' if multiplier==1 else 'ms'}


def download_day(root,symbol,day,budget,max_archive):
    base=f'{symbol}-aggTrades-{day:%Y-%m-%d}'
    archive=root/(base+'.zip');flow=root/(base+'-flow.csv');manifest=root/(base+'.json')
    converter=sha256(Path(__file__))
    if manifest.exists():
        m=json.loads(manifest.read_text())
        if m['symbol']!=symbol or m['date']!=day.strftime('%Y-%m-%d') or m['converter_sha256']!=converter:
            raise ValueError('Existing manifest identity/version differs; use a new root')
        if sha256(archive)!=m['archive_sha256'] or sha256(flow)!=m['flow_sha256']:
            raise ValueError('Existing artifact failed integrity check')
        print(f'[tradeflow] reused verified {base}',flush=True);return m
    url=f'https://data.binance.vision/data/spot/daily/aggTrades/{symbol}/{base}.zip'
    check=root/(base+'.checksum.partial');part=root/(base+'.zip.partial');temp=root/(base+'-flow.partial')
    try:
        print(f'[tradeflow] downloading/verifying {base}',flush=True)
        fetch(url+'.CHECKSUM',check,root,budget,4096)
        fields=check.read_text().strip().split()
        if len(fields)!=2 or not re.fullmatch(r'[0-9a-fA-F]{64}',fields[0]) or fields[1].lstrip('*')!=base+'.zip':
            raise ValueError('Unexpected archive checksum format/name')
        expected=fields[0].lower()
        if archive.exists():
            if sha256(archive)!=expected:raise ValueError('Existing raw archive checksum mismatch; preserve and inspect it')
        else:
            fetch(url,part,root,budget,max_archive)
            if sha256(part)!=expected:raise ValueError('Downloaded archive checksum mismatch')
            part.replace(archive)
        stats=convert(archive,temp,day,root,budget)
        digest=sha256(temp)
        temp.replace(flow)
        m={'venue':'binance','market':'spot','kind':'aggTrades','symbol':symbol,'date':day.strftime('%Y-%m-%d'),
           'source_url':url,'archive_sha256':expected,'flow_sha256':digest,'converter_sha256':converter,
           'archive_bytes':archive.stat().st_size,'flow_bytes':flow.stat().st_size,**stats,
           'note':'Closed-minute trade-flow summaries, not order-book depth or executable quotes; no model approval.'}
        space(root,budget,8192);atomic_json(manifest,m)
        print(f'[tradeflow] complete: {json.dumps(m)}',flush=True)
        return m
    finally:
        for p in (check,part,temp):p.unlink(missing_ok=True)


def run(root,symbol,start,end,reserve_from,max_total_gib=8,max_archive_mib=512):
    if not re.fullmatch('[A-Z0-9]{2,24}',symbol):raise ValueError('Use an uppercase Binance symbol')
    start,end,reserve=[datetime.strptime(v,'%Y-%m-%d').replace(tzinfo=timezone.utc) for v in (start,end,reserve_from)]
    if not start<end<=reserve or end>datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0):
        raise ValueError('Require past complete days with start < end <= reserved date')
    if (end-start).days>31:raise ValueError('Acquire at most 31 days per invocation')
    if not 1<=max_total_gib<=1000 or not 1<=max_archive_mib<=2048:raise ValueError('Invalid storage limits')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with process_lock(root/'download.lock'):
        space(root,max_total_gib*GIB)
        reports=[];day=start
        while day<end:
            reports.append(download_day(root,symbol,day,max_total_gib*GIB,max_archive_mib*1024**2))
            day+=timedelta(days=1)
    summary={'days':len(reports),'agg_events':sum(m['agg_events'] for m in reports),
             'archive_bytes':sum(m['archive_bytes'] for m in reports),'flow_bytes':sum(m['flow_bytes'] for m in reports),
             'empty_minutes':sum(m['empty_minutes'] for m in reports),'aggregate_id_gaps':sum(m['aggregate_id_gaps'] for m in reports),
             'reserve_from':reserve.strftime('%Y-%m-%d'),'approved':False}
    print(json.dumps(summary,indent=2));return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol',required=True);p.add_argument('--start',required=True);p.add_argument('--end',required=True)
    p.add_argument('--reserve-from',required=True);p.add_argument('--root',type=Path,default=Path('data/tradeflow'))
    p.add_argument('--max-total-gib',type=int,default=8);p.add_argument('--max-archive-mib',type=int,default=512)
    a=p.parse_args()
    try:run(a.root,a.symbol,a.start,a.end,a.reserve_from,a.max_total_gib,a.max_archive_mib);return 0
    except KeyboardInterrupt:print('Interrupted; rerun to reuse completed days.',file=sys.stderr);return 130
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,zipfile.BadZipFile,csv.Error,DecimalException) as error:
        print(f'Trade-flow acquisition stopped: {error}',file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
