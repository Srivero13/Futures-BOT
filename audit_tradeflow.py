"""Verify closed-minute trade-flow alignment against the existing candle corpus."""
import argparse
import csv
from decimal import Decimal, DecimalException, localcontext
import json
from pathlib import Path
import sys

from engine_v1.dataset import candles, sha256
from engine_v1.operations import atomic_json
from train_v15 import timestamp


def dec(value):
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Non-finite source value')
    return result


def compare(flow,candle):
    with localcontext() as ctx:
        ctx.prec=50
        buy,sell=dec(flow['taker_buy_qty']),dec(flow['taker_sell_qty'])
        first,last=dec(flow['first_price']),dec(flow['last_price'])
        if min(buy,sell)<0 or buy+sell<=0 or min(first,last)<=0:
            raise ValueError('Invalid flow quantities/prices')
        volume=dec(candle['volume']);difference=buy+sell-volume
        tolerance=Decimal('1e-8')+abs(volume)*Decimal('1e-10')
        return {'open_match':first==dec(candle['open']), 'close_match':last==dec(candle['close']),
                'endpoints_within_candle_range':dec(candle['low'])<=min(first,last)<=max(first,last)<=dec(candle['high']),
                'volume_exact_match':difference==0,'volume_within_tolerance':abs(difference)<=tolerance,
                'volume_difference':str(difference),'volume_tolerance':str(tolerance)}


def run(flow_paths,candle_paths,symbol,reserve_from,output):
    reserve=timestamp(reserve_from);output=Path(output)
    if output.exists():raise ValueError('Output exists; choose a new filename')
    flow_paths=[Path(p).resolve() for p in flow_paths];candle_paths=[Path(p).resolve() for p in candle_paths]
    if not flow_paths or len(flow_paths)>31 or len(set(flow_paths))!=len(flow_paths):
        raise ValueError('Supply 1..31 unique daily flow files')
    if not candle_paths or len(set(candle_paths))!=len(candle_paths):raise ValueError('Supply unique chronological candle files')
    fingerprints={};flow={};days={}
    def remember(path):
        digest=sha256(path);fingerprints[str(path)]=digest;return digest
    print('[flow-audit] verifying raw archives, summaries and candles',flush=True)
    for path in flow_paths:
        if not path.name.endswith('-flow.csv'):raise ValueError('Expected daily -flow.csv files')
        stem=path.name[:-len('-flow.csv')];meta_path=path.with_name(stem+'.json');archive=path.with_name(stem+'.zip')
        remember(meta_path);meta=json.loads(meta_path.read_text())
        if (meta['venue'],meta['market'],meta['kind'],meta['symbol'])!=('binance','spot','aggTrades',symbol):
            raise ValueError('Flow source identity mismatch')
        start=timestamp(meta['date']);end=start+86400000
        if end>reserve or meta['date'] in days:raise ValueError('Reserved or duplicate flow day')
        if remember(path)!=meta['flow_sha256'] or remember(archive)!=meta['archive_sha256']:
            raise ValueError('Flow/raw archive checksum mismatch')
        observed=events=0
        with path.open(newline='') as f:
            for row in csv.DictReader(f):
                ts=int(row['timestamp'])*1000
                if ts%60000 or not start<=ts<end or ts in flow or int(row['available_at_ms'])!=ts+60000:
                    raise ValueError('Duplicate, misaligned or premature flow timestamp')
                count=int(row['agg_events'])
                if count<=0:raise ValueError('Invalid aggregate event count')
                flow[ts]=row;observed+=1;events+=count
        if observed!=meta['observed_minutes'] or events!=meta['agg_events'] or 1440-observed!=meta['empty_minutes']:
            raise ValueError('Flow statistics disagree with manifest')
        days[meta['date']]={'start_ms':start,'end_ms':end,'flow_minutes':observed,'candle_minutes':0}
    for path in candle_paths:
        meta_path=path.with_suffix('.json');remember(meta_path);meta=json.loads(meta_path.read_text())
        if (meta['venue'],meta['symbol'],meta['timeframe_ms'])!=('binance',symbol,60000):
            raise ValueError('Candle source identity mismatch')
        if type(meta.get('last_open_ms')) is not int or meta['last_open_ms']>=reserve:
            raise ValueError('Candle shard reaches reserved dates or lacks coverage metadata')
        if remember(path)!=meta['sha256']:raise ValueError('Candle checksum mismatch')
    metrics={k:0 for k in ('matched_minutes','open_mismatches','close_mismatches','range_mismatches','volume_exact_mismatches','volume_tolerance_mismatches')}
    seen=set();samples=[];max_difference=Decimal(0)
    for candle in candles(candle_paths):
        ts=candle['timestamp']
        if ts>=reserve:raise ValueError('Candle reaches reserved dates despite metadata')
        for day in days.values():
            if day['start_ms']<=ts<day['end_ms']:day['candle_minutes']+=1
        if ts not in flow:continue
        seen.add(ts);result=compare(flow[ts],candle);metrics['matched_minutes']+=1
        for key,field in [('open_mismatches','open_match'),('close_mismatches','close_match'),
                          ('range_mismatches','endpoints_within_candle_range'),('volume_exact_mismatches','volume_exact_match'),
                          ('volume_tolerance_mismatches','volume_within_tolerance')]:
            metrics[key]+=int(not result[field])
        max_difference=max(max_difference,abs(Decimal(result['volume_difference'])))
        if not all(result[k] for k in ('open_match','close_match','endpoints_within_candle_range','volume_within_tolerance')) and len(samples)<20:
            samples.append({'timestamp_ms':ts,**result})
    metrics.update(days=len(days),flow_minutes=len(flow),flow_without_candle=len(flow)-len(seen),
        missing_flow_minutes=sum(1440-d['flow_minutes'] for d in days.values()),
        missing_candle_minutes=sum(1440-d['candle_minutes'] for d in days.values()),
        max_absolute_volume_difference=str(max_difference))
    passed=bool(flow) and not any(metrics[k] for k in ('open_mismatches','close_mismatches','range_mismatches',
         'volume_tolerance_mismatches','flow_without_candle','missing_flow_minutes','missing_candle_minutes'))
    metrics['alignment_passed']=passed
    if any(sha256(Path(p))!=digest for p,digest in fingerprints.items()):raise ValueError('Inputs changed during audit')
    report={'approved':False,'summary':metrics,'days':days,'mismatch_examples':samples,
        'spec':{'symbol':symbol,'reserve_from':reserve_from,'input_sha256':fingerprints,'runner_sha256':sha256(Path(__file__))},
        'limitations':['Alignment is not a strategy result, data authenticity certificate, or approval.',
          'Only first/last trade prices and summed base quantity are compared; high/low checks cover endpoints, not every raw trade.',
          'Volume tolerance is fixed at 1e-8 base units plus 1e-10 times candle volume; exact mismatch counts remain visible.',
          'Empty minutes prevent a full-coverage pass; missing data are not fabricated.',
          'Flow is available at minute close in event time, not necessarily at that instant in live receipt time.']}
    atomic_json(output,report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--flow-files',type=Path,nargs='+',required=True)
    p.add_argument('--candle-files',type=Path,nargs='+',required=True)
    p.add_argument('--symbol',required=True);p.add_argument('--reserve-from',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        report=run(a.flow_files,a.candle_files,a.symbol,a.reserve_from,a.output)
        print(json.dumps(report['summary'],indent=2));print(f'Completed: {a.output}; audit only, unapproved.')
        return 0 if report['summary']['alignment_passed'] else 1
    except (ValueError,OSError,KeyError,TypeError,DecimalException,csv.Error) as error:
        print(f'Flow alignment audit stopped: {error}',file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('Interrupted; no complete report published.',file=sys.stderr);return 130


if __name__=='__main__':raise SystemExit(main())
