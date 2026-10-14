"""Bounded spot/USD-M best-quote pilot. Public data only; no orders or P&L."""
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
from queue import Queue, Empty, Full
import re
from threading import Event, Thread
import time

import websocket
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from record_market import Writer, StorageLimit


def quote(raw, venue, symbol, mono, wall):
    d=json.loads(raw)
    if d.get('s')!=symbol or type(d.get('u')) is not int or d['u']<0:
        raise ValueError('Invalid quote identity')
    if venue=='usdm' and (d.get('e')!='bookTicker' or d.get('st',1)!=1):
        raise ValueError('Expected USD-M book ticker')
    values={}
    for key in ('b','a','B','A'):
        if not isinstance(d.get(key),str): raise ValueError('Expected decimal quote strings')
        v=Decimal(d[key])
        if not v.is_finite() or v<=0: raise ValueError('Invalid quote price or size')
        values[key]=v
    if values['b']>values['a']: raise ValueError('Crossed quote')
    for key in ('E','T'):
        if key in d and (type(d[key]) is not int or d[key]<0): raise ValueError('Invalid source timestamp')
    return dict(kind='quote',venue=venue,symbol=symbol,update_id=d['u'],
                bid=d['b'],ask=d['a'],bid_size=d['B'],ask_size=d['A'],
                source_event_ms=d.get('E'),source_transaction_ms=d.get('T'),
                receipt_monotonic_ns=mono,receipt_wall_ns=wall)


def pair(latest, now, max_age_ns=250000000):
    if set(latest)!= {'spot','usdm'}: return None
    ages={v:now-q['receipt_monotonic_ns'] for v,q in latest.items()}
    if any(a<0 or a>max_age_ns for a in ages.values()): return None
    return dict(kind='receipt_pair',paired_monotonic_ns=now,ages_ns=ages,
                receipt_skew_ns=abs(ages['spot']-ages['usdm']),
                spot=latest['spot'],usdm=latest['usdm'])


def feed(venue,url,symbol,queue,stop,failures):
    ws=None
    try:
        ws=websocket.create_connection(url,timeout=3)
        ws.settimeout(1)
        last_receipt=time.monotonic()
        last_id=-1
        while not stop.is_set():
            try: raw=ws.recv()
            except websocket.WebSocketTimeoutException:
                if time.monotonic()-last_receipt>10: raise TimeoutError('Quote feed idle')
                continue
            mono,wall=time.monotonic_ns(),time.time_ns()
            if not raw: raise ConnectionError('Quote feed closed')
            if len(raw)>16384: raise ValueError('Oversize quote')
            q=quote(raw,venue,symbol,mono,wall)
            if q['update_id']<=last_id: raise ValueError('Nonincreasing quote update ID')
            last_id=q['update_id'];last_receipt=time.monotonic()
            queue.put_nowait(q)
    except Exception as error:
        failures.put((venue,type(error).__name__))
        stop.set()
    finally:
        if ws is not None:
            try: ws.close(timeout=1)
            except Exception: pass


def capture(symbol,seconds,root,max_mib):
    if not re.fullmatch('[A-Z0-9]{3,20}',symbol): raise ValueError('Invalid symbol')
    if not 1<=seconds<=600 or not 1<=max_mib<=1024:
        raise ValueError('Pilot requires 1..600 seconds and 1..1024 MiB')
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    urls={'spot':f'wss://stream.binance.com:9443/ws/{symbol.lower()}@bookTicker',
          'usdm':f'wss://fstream.binance.com/public/ws/{symbol.lower()}@bookTicker'}
    queue=Queue(maxsize=4096);failures=Queue();stop=Event();threads=[]
    writer=Writer(root,max_mib*1024**2)
    counts=Counter();latest={};reason='duration';started=time.monotonic();last_progress=started
    atomic_json(root/'protocol.json',dict(approved=False,observe_only=True,symbol=symbol,
        endpoints=urls,seconds=seconds,max_mib=max_mib,max_receipt_age_ms=250,
        runner_sha256=sha256(Path(__file__)),writer_sha256=sha256(Path(__file__).with_name('record_market.py'))))
    try:
        for venue,url in urls.items():
            t=Thread(target=feed,args=(venue,url,symbol,queue,stop,failures),daemon=True)
            threads.append(t);t.start()
        while time.monotonic()-started<seconds and not stop.is_set():
            try: q=queue.get(timeout=min(.2,max(.001,seconds-(time.monotonic()-started))))
            except Empty: q=None
            if q is not None:
                if stop.is_set(): break
                writer.write(q);counts[q['venue']+'_quotes']+=1;latest[q['venue']]=q
                p=pair(latest,time.monotonic_ns())
                if p is not None:
                    writer.write(p);counts['receipt_pairs']+=1
                else: counts['unpaired_updates']+=1
            if time.monotonic()-last_progress>=5:
                writer.flush();last_progress=time.monotonic()
                print(f'[basis-record] elapsed={last_progress-started:.0f}/{seconds}s counts={dict(counts)} bytes={writer.total}',flush=True)
        if stop.is_set(): reason='feed_failure'
    except StorageLimit as error: reason=str(error)
    except KeyboardInterrupt: reason='interrupted'
    except OSError: reason='storage_or_os_error'
    finally:
        stop.set()
        for t in threads: t.join(timeout=4)
        writer.close_part()
    errors=[]
    while not failures.empty(): errors.append(failures.get_nowait())
    if errors and reason=='duration': reason='feed_failure'
    alive=any(t.is_alive() for t in threads)
    if alive: reason='worker_shutdown_timeout'
    report=dict(approved=False,observe_only=True,stop_reason=reason,
        capture_completed=reason=='duration' and counts['receipt_pairs']>0,
        elapsed_seconds=time.monotonic()-started,counts=dict(counts),errors=errors,
        event_bytes=writer.total,parts=writer.parts,workers_stopped=not alive,
        limitations=['Receipt-time pairs are not exchange-synchronized quotes or guaranteed fills.',
          'Spot bookTicker has no source event timestamp; socket buffering and asymmetric latency remain unknown.',
          'Pairs reuse the latest opposite quote and are not independent observations.',
          'No reconnect, gap backfill, depth reconstruction, costs, funding or P&L; pilot only.',
          'Receipt freshness is a 250ms local engineering filter, not an execution guarantee.',
          'Power loss can leave incomplete data or no summary; wall-clock jumps are not corrected.'])
    atomic_json(root/'summary.json',report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol',default='ETHUSDT')
    p.add_argument('--seconds',type=int,default=60)
    p.add_argument('--max-mib',type=int,default=64)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    r=capture(a.symbol,a.seconds,a.output_dir,a.max_mib)
    print(json.dumps(r,indent=2))
    return 0 if r['capture_completed'] else 2


if __name__=='__main__': raise SystemExit(main())
