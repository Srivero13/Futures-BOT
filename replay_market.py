"""Verify recorded files and replay a snapshot-bounded spot order book offline."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import time
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from record_market import DepthSequence


def number(value):
    d=Decimal(str(value))
    if not d.is_finite():raise ValueError('Non-finite price/quantity')
    return d


def levels(rows, snapshot=False):
    result={}
    for row in rows:
        if len(row)!=2:raise ValueError('Invalid level')
        price,qty=map(number,row)
        if price<=0 or qty<0 or (snapshot and qty==0) or price in result:
            raise ValueError('Invalid or duplicate level')
        result[price]=qty
    return result


class Book:
    def __init__(self,data):
        self.sequence=DepthSequence(data['lastUpdateId'])
        self.bids=levels(data['bids'],True);self.asks=levels(data['asks'],True)
        if not self.bids or not self.asks:raise ValueError('Empty snapshot')
        self.bid_floor=min(self.bids);self.ask_ceiling=max(self.asks)
        self.quote()

    def quote(self):
        if not self.bids or not self.asks:return None
        bid,ask=max(self.bids),min(self.asks)
        if bid>=ask:raise ValueError('Crossed or locked reconstructed book')
        return bid,ask,self.bids[bid],self.asks[ask]

    def update(self,data):
        status=self.sequence.accept(data['U'],data['u'])
        if status=='stale':return status,None
        updates=[levels(data['b']),levels(data['a'])]
        # Unknown levels beyond the original snapshot are never treated as complete.
        for side,changes,is_bid in ((self.bids,updates[0],True),(self.asks,updates[1],False)):
            for price,qty in changes.items():
                if (is_bid and price<self.bid_floor) or (not is_bid and price>self.ask_ceiling):continue
                if qty==0:side.pop(price,None)
                else:side[price]=qty
            if len(side)>200000:raise ValueError('Book level memory cap reached')
        return status,self.quote()


def replay(root,output,on_quote=None):
    root=Path(root).resolve();output=Path(output)
    if output.exists():raise ValueError('Output exists; choose another filename')
    summary_path=root/'summary.json';protocol_path=root/'protocol.json'
    source_hashes={str(p):sha256(p) for p in (summary_path,protocol_path)}
    summary=json.loads(summary_path.read_text());protocol=json.loads(protocol_path.read_text())
    parts=summary['parts'];names=[p['file'] for p in parts]
    if not parts or any(not re.fullmatch(r'events-\d{5}\.jsonl',n) for n in names):raise ValueError('Invalid part names')
    if names!=[f'events-{i:05d}.jsonl' for i in range(len(parts))]:raise ValueError('Missing, duplicate or unordered parts')
    if set(names)!={p.name for p in root.glob('events-*.jsonl')}:raise ValueError('Unlisted event files')
    if sum(p['bytes'] for p in parts)!=summary['event_bytes']:raise ValueError('Manifest byte sum mismatch')
    print('[replay] verifying file sizes and SHA-256',flush=True)
    for p in parts:
        path=root/p['file']
        if path.stat().st_size!=p['bytes'] or sha256(path)!=p['sha256']:raise ValueError('Corrupt part: '+p['file'])
    counts=Counter();book=None;session=None;last_mono=None;last_depth_mono=None
    max_depth_gap=0;last_trade=None;spread_sum=0.;spread_max=0.;spread_min=None
    epochs=[];epoch=None
    imbalance_sum=0.;lines=0;started=time.monotonic();read_bytes=0
    for part in parts:
        digest=hashlib.sha256()
        with (root/part['file']).open('rb') as handle:
            for raw in handle:
                digest.update(raw);read_bytes+=len(raw);lines+=1
                if not raw.endswith(b'\n'):raise ValueError('Incomplete final record')
                record=json.loads(raw);kind=record['kind'];sid=record['session']
                if on_quote is not None and (kind in ('session_start','session_error','snapshot','snapshot_refresh','unexpected_event') or record.get('clock_jump',False)):
                    on_quote(record,None)
                mono=record['receipt_monotonic_ns']
                if type(mono) is not int or (last_mono is not None and mono<last_mono):raise ValueError('Non-monotonic receipt times')
                last_mono=mono
                if kind=='session_start':
                    if session is not None and sid<=session:raise ValueError('Non-increasing session')
                    session=sid;book=None;last_depth_mono=None;counts['session_starts']+=1
                elif kind=='session_error':
                    book=None;last_depth_mono=None;counts['session_errors']+=1
                else:
                    if sid!=session:raise ValueError('Event without its session')
                    data=record['data']
                    if kind in ('snapshot','snapshot_refresh'):
                        if kind=='snapshot' and book is not None:raise ValueError('Duplicate session snapshot')
                        if kind=='snapshot_refresh':
                            if book is None:raise ValueError('Refresh without active book')
                            if int(data['lastUpdateId'])<book.sequence.last:raise ValueError('Refresh sequence regressed')
                            counts['snapshot_refreshes']+=1
                        book=Book(data);counts['snapshots']+=1;last_depth_mono=None
                        epoch={'session':sid,'snapshot_sequence':book.sequence.last,'covered_quotes':0,'uncovered_quotes':0}
                        epochs.append(epoch)
                    elif kind in ('aggTrade','depthUpdate'):
                        if data['s']!=protocol['symbol'] or data['e']!=kind:raise ValueError('Event identity mismatch')
                        counts['clock_jumps']+=int(record.get('clock_jump',False))
                        if kind=='aggTrade':
                            if number(data['p'])<=0 or number(data['q'])<=0:raise ValueError('Invalid trade')
                            trade=int(data['a'])
                            if last_trade is not None:
                                if trade>last_trade+1:counts['aggregate_id_missing']+=trade-last_trade-1
                                elif trade<=last_trade:counts['aggregate_id_stale']+=1
                            last_trade=max(trade,last_trade if last_trade is not None else trade)
                            counts['agg_trades']+=1
                        else:
                            if book is None:raise ValueError('Depth without valid snapshot')
                            try:status,quote=book.update(data)
                            except ValueError as error:
                                if str(error)!='depth_sequence_gap' or record['sequence_status']!='gap_or_invalid':raise
                                counts['depth_gap_or_invalid']+=1;book=None;last_depth_mono=None
                                if on_quote is not None:on_quote(record,None)
                                continue
                            if status!=record['sequence_status']:raise ValueError('Recorded sequence status mismatch')
                            counts['depth_'+status]+=1
                            if status=='linked':
                                if on_quote is not None:on_quote(record,quote)
                                if last_depth_mono is not None:max_depth_gap=max(max_depth_gap,(mono-last_depth_mono)/1e6)
                                last_depth_mono=mono
                                if quote is None:
                                    counts['uncovered_quotes']+=1;epoch['uncovered_quotes']+=1
                                else:
                                    bid,ask,bq,aq=quote
                                    spread=float((ask-bid)/((ask+bid)/2)*10000)
                                    counts['covered_quotes']+=1;epoch['covered_quotes']+=1;spread_sum+=spread
                                    spread_max=max(spread_max,spread);spread_min=spread if spread_min is None else min(spread_min,spread)
                                    imbalance_sum+=float((bq-aq)/(bq+aq))
                    elif kind=='unexpected_event':
                        counts['unexpected_events']+=1;book=None
                    else:raise ValueError('Unknown record kind')
                if lines%50000==0:print(f'[replay] records={lines:,} elapsed={time.monotonic()-started:.1f}s',flush=True)
        if digest.hexdigest()!=part['sha256']:raise ValueError('Part changed during replay')
    for key in ('snapshots','snapshot_refreshes','agg_trades','depth_stale','depth_linked','depth_gap_or_invalid','clock_jumps','aggregate_id_missing','aggregate_id_stale'):
        if counts[key]!=summary['counts'].get(key,0):raise ValueError('Recorder count mismatch: '+key)
    if read_bytes!=summary['event_bytes']:raise ValueError('Replay byte count mismatch')
    if any(sha256(Path(p))!=h for p,h in source_hashes.items()):raise ValueError('Metadata changed during replay')
    n=counts['covered_quotes']
    result={'approved':False,'capture':str(root),'integrity_passed':True,'counts':dict(counts),
        'snapshot_epochs':epochs,
        'covered_depth_fraction':n/counts['depth_linked'] if counts['depth_linked'] else None,
        'records':lines,'max_linked_depth_receipt_gap_ms':max_depth_gap,
        'covered_quote_spread_bps':{'mean':spread_sum/n if n else None,'min':spread_min,'max':spread_max if n else None},
        'mean_best_level_quantity_imbalance':imbalance_sum/n if n else None,
        'source_metadata_sha256':source_hashes,'parts':parts,'runner_sha256':sha256(Path(__file__)),
        'limitations':['Replay checks internal consistency, not exchange authenticity or profitability.',
        'Book includes only prices within initial snapshot coverage boundaries; empty sides produce uncovered quotes.',
        'Quote statistics are event-weighted, not time-weighted; no inference between updates.',
        'Receipt gaps include buffering and processing and are not network RTT.',
        'No merging across sessions or captures, fill simulation, model training or approval.']}
    atomic_json(output,result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        report=replay(a.capture,a.output)
        print(json.dumps({k:v for k,v in report.items() if k not in ('parts','source_metadata_sha256','limitations','snapshot_epochs')},indent=2))
        print(f'Completed: {a.output}; replay only, unapproved.')
    except (ValueError,OSError,KeyError,TypeError,InvalidOperation) as error:
        print(f'Replay stopped: {error}');return 2
    except KeyboardInterrupt:return 130
    return 0


if __name__=='__main__':raise SystemExit(main())
