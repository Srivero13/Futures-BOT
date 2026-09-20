"""Read-only spot research capture with snapshot-linked depth sequence checks."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from urllib.request import urlopen
from urllib.error import URLError
import websocket
from engine_v1.operations import atomic_json


class StorageLimit(Exception):
    pass


class DepthSequence:
    def __init__(self, snapshot_id):
        self.last=int(snapshot_id)
        if self.last<0:raise ValueError('Invalid snapshot sequence')
        self.bridged=False

    def accept(self, first, last):
        first,last=int(first),int(last)
        if first<0 or last<first:raise ValueError('Invalid depth sequence range')
        if last<=self.last:return 'stale'
        if first>self.last+1:raise ValueError('depth_sequence_gap')
        self.last=last;self.bridged=True
        return 'linked'


class Writer:
    def __init__(self,root,limit,chunk=64*1024**2,reserve=1024**3):
        self.root=Path(root);self.limit=limit;self.chunk=chunk;self.reserve=reserve
        self.total=0;self.handle=None;self.size=0;self.parts=[]

    def close_part(self):
        if self.handle:
            self.handle.flush();self.handle.close()
            self.parts.append({'file':self.path.name,'bytes':self.size,'sha256':self.digest.hexdigest()})
            self.handle=None

    def write(self,record):
        payload=(json.dumps(record,separators=(',',':'),allow_nan=False)+'\n').encode()
        if self.total+len(payload)>self.limit:raise StorageLimit('byte_budget')
        if shutil.disk_usage(self.root).free-len(payload)<self.reserve:raise StorageLimit('disk_reserve')
        if self.handle and self.size+len(payload)>self.chunk:self.close_part()
        if self.handle is None:
            self.path=self.root/f'events-{len(self.parts):05d}.jsonl'
            self.handle=self.path.open('xb');self.size=0;self.digest=hashlib.sha256()
        self.handle.write(payload);self.digest.update(payload)
        self.total+=len(payload);self.size+=len(payload)

    def flush(self):
        if self.handle:self.handle.flush()


def stamps():
    return {'receipt_wall_ns':time.time_ns(),'receipt_monotonic_ns':time.monotonic_ns()}


def capture(symbol,seconds,root,max_bytes,snapshot_seconds=300):
    if not re.fullmatch('[A-Z0-9]{3,20}',symbol):raise ValueError('Invalid symbol')
    if not 1<=seconds<=86400 or not 1024**2<=max_bytes<=32*1024**3:
        raise ValueError('Use 1..86400 seconds and 1 MiB..32 GiB')
    if not 30<=snapshot_seconds<=3600:raise ValueError('Use 30..3600 seconds between snapshots')
    root=Path(root);root.mkdir(parents=True,exist_ok=False)
    url=f'wss://stream.binance.com:9443/stream?streams={symbol.lower()}@aggTrade/{symbol.lower()}@depth@100ms'
    snapshot_url=f'https://api.binance.com/api/v3/depth?symbol={symbol}&limit=1000'
    atomic_json(root/'protocol.json',{'symbol':symbol,'seconds':seconds,'max_event_bytes':max_bytes,
        'snapshot_seconds':snapshot_seconds,'format_version':2,
        'streams_url':url,'snapshot_url':snapshot_url,'timestamp_unit':'exchange milliseconds; receipt nanoseconds',
        'approved':False,'purpose':'Prospective development capture; never an untouched September holdout',
        'note':'Receipt means application read completion, not kernel packet arrival. No orders or book reconstruction.'})
    writer=Writer(root,max_bytes);counts=Counter();errors=Counter();session=0
    started=time.monotonic();deadline=started+seconds;progress=started;reason='duration';failures=0
    last_trade=None;previous_clock=None
    try:
        while time.monotonic()<deadline:
            ws=None;session+=1
            try:
                ws=websocket.create_connection(url,timeout=min(5,max(.1,deadline-time.monotonic())))
                writer.write({'kind':'session_start','session':session,**stamps()})
                def get_snapshot(previous=None):
                    before=stamps()
                    with urlopen(snapshot_url,timeout=min(5,max(.1,deadline-time.monotonic()))) as response:
                        raw=response.read(2*1024**2+1)
                    after=stamps()
                    if len(raw)>2*1024**2:raise ValueError('Oversized snapshot')
                    snapshot=json.loads(raw)
                    if not isinstance(snapshot.get('bids'),list) or not isinstance(snapshot.get('asks'),list):
                        raise ValueError('Invalid snapshot')
                    new_chain=DepthSequence(snapshot['lastUpdateId'])
                    if previous is not None and new_chain.last<previous.last:
                        raise ValueError('Refresh snapshot behind current depth sequence')
                    refresh=previous is not None
                    writer.write({'kind':'snapshot_refresh' if refresh else 'snapshot','session':session,
                        'request_started':before,**after,'data':snapshot})
                    counts['snapshots']+=1
                    if refresh:counts['snapshot_refreshes']+=1
                    return new_chain
                chain=get_snapshot();idle=time.monotonic();refresh_at=idle+snapshot_seconds
                while time.monotonic()<deadline:
                    if time.monotonic()>=refresh_at:
                        chain=get_snapshot(chain)
                        refresh_at=time.monotonic()+snapshot_seconds
                        print(f'[record] refreshed snapshot session={session} sequence={chain.last}',flush=True)
                        if time.monotonic()>=deadline:break
                    ws.settimeout(min(1,max(.01,deadline-time.monotonic())))
                    try:
                        raw=ws.recv();receipt=stamps()
                    except websocket.WebSocketTimeoutException:
                        if time.monotonic()-idle>30:raise ValueError('feed_idle_30s')
                        continue
                    if not raw:raise ValueError('feed_closed')
                    idle=time.monotonic()
                    if len(raw)>2*1024**2:raise ValueError('Oversized stream event')
                    event=json.loads(raw);data=event.get('data',{});kind=data.get('e')
                    if kind not in ('depthUpdate','aggTrade') or data.get('s')!=symbol:
                        writer.write({'kind':'unexpected_event','session':session,**receipt,'data':event})
                        raise ValueError('Unexpected stream event')
                    status='recorded';gap=False
                    if kind=='depthUpdate':
                        try:status=chain.accept(data['U'],data['u'])
                        except ValueError:status='gap_or_invalid';gap=True
                        counts['depth_'+status]+=1
                    else:
                        trade=int(data['a'])
                        if last_trade is not None:
                            if trade>last_trade+1:counts['aggregate_id_missing']+=trade-last_trade-1
                            elif trade<=last_trade:counts['aggregate_id_stale']+=1
                        last_trade=max(last_trade if last_trade is not None else trade,trade)
                        counts['agg_trades']+=1
                    clock=(receipt['receipt_wall_ns'],receipt['receipt_monotonic_ns'])
                    jump=previous_clock is not None and abs((clock[0]-previous_clock[0])-(clock[1]-previous_clock[1]))>100_000_000
                    previous_clock=clock
                    counts['clock_jumps']+=int(jump)
                    writer.write({'kind':kind,'session':session,**receipt,'sequence_status':status,
                        'clock_jump':jump,'data':data})
                    if gap:raise ValueError('depth_sequence_gap')
                    failures=0
                    if time.monotonic()-progress>=10:
                        writer.flush();progress=time.monotonic()
                        print(f'[record] elapsed={progress-started:.0f}/{seconds}s bytes={writer.total} sessions={session} counts={dict(counts)}',flush=True)
            except (websocket.WebSocketException,URLError,TimeoutError,ConnectionError,ValueError,KeyError) as error:
                name=str(error) if isinstance(error,ValueError) else type(error).__name__
                errors[name]+=1;failures+=1
                writer.write({'kind':'session_error','session':session,**stamps(),'error':name})
                print(f'[record] session={session} reconnect: {name}',flush=True)
                if failures>=10:reason='consecutive_failure_limit';break
            finally:
                if ws is not None:ws.close(timeout=1)
            remaining=deadline-time.monotonic()
            if remaining>0:time.sleep(min(remaining,2**min(failures,5)))
    except StorageLimit as error:reason=str(error)
    except KeyboardInterrupt:reason='interrupted'
    except OSError as error:
        reason='storage_or_os_error';errors[type(error).__name__]+=1
    finally:
        writer.close_part()
        summary={'approved':False,'observe_only':True,'stop_reason':reason,'elapsed_seconds':time.monotonic()-started,
            'sessions':session,'counts':dict(counts),'errors':dict(errors),'event_bytes':writer.total,'parts':writer.parts,
            'limitations':['Sequence-linked depth is not a reconstructed or validated executable book.',
            'Snapshots contain at most 1000 levels per side; unchanged deeper levels are unknown.',
            'Snapshot fetching temporarily delays application reads; socket buffering is included in receipt timing.',
            'No clock-offset estimate: event-to-receipt differences are not RTT or pure network latency.',
            'Disconnect intervals and trade gaps are not backfilled; no claim of complete market coverage.',
            'Flush every 10 seconds; abrupt termination may leave an incomplete last line or missing manifest.']}
        atomic_json(root/'summary.json',summary)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol',default='ETHUSDT');p.add_argument('--seconds',type=int,default=21600)
    p.add_argument('--snapshot-seconds',type=int,default=300)
    p.add_argument('--max-gib',type=float,default=4);p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    try:
        result=capture(a.symbol,a.seconds,a.output_dir,int(a.max_gib*1024**3),a.snapshot_seconds)
        print(json.dumps(result,indent=2))
        return 0 if result['stop_reason'] in ('duration','byte_budget','disk_reserve','interrupted') else 2
    except (OSError,ValueError,OverflowError) as error:
        print(f'Recorder stopped: {error}');return 2


if __name__=='__main__':raise SystemExit(main())
