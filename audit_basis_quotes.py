"""Offline integrity and receipt-pair replay for completed quote pilots."""
import argparse
from collections import Counter
import json
from pathlib import Path

from engine_v1.dataset import sha256
from engine_v1.research_artifacts import read_json
from record_basis_quotes import quote, pair


def audit(root):
    root=Path(root)
    summary,summary_hash=read_json(root/'summary.json')
    protocol,protocol_hash=read_json(root/'protocol.json')
    if (summary.get('capture_completed') is not True or summary.get('stop_reason')!='duration'
            or summary.get('workers_stopped') is not True or summary.get('errors')!=[]
            or summary.get('approved') is not False or summary.get('observe_only') is not True):
        raise ValueError('Require a normally completed observation pilot without feed errors')
    if (protocol.get('max_receipt_age_ms')!=250 or protocol.get('approved') is not False
            or protocol.get('observe_only') is not True):
        raise ValueError('Unsupported capture protocol')
    parts=summary['parts']
    if not parts: raise ValueError('No saved quote parts')
    hashes={'summary.json':summary_hash,'protocol.json':protocol_hash}
    total=0
    for i,part in enumerate(parts):
        name=part['file']
        if name!=f'events-{i:05d}.jsonl' or (root/name).is_symlink():
            raise ValueError('Unexpected part path or order')
        size=(root/name).stat().st_size
        if type(part['bytes']) is not int or size!=part['bytes'] or sha256(root/name)!=part['sha256']:
            raise ValueError('Quote part size/hash mismatch')
        hashes[name]=part['sha256'];total+=size
    if total!=summary['event_bytes'] or total>protocol['max_mib']*1024**2:
        raise ValueError('Byte totals do not reconcile')
    latest={};counts=Counter();reuse=Counter();last_pair={};pending=False;last_pair_time=-1
    stats={k:dict(count=0,sum=0,min=None,max=None) for k in ('spot_age','usdm_age','skew')}
    def observe(name,value):
        s=stats[name];s['count']+=1;s['sum']+=value
        s['min']=value if s['min'] is None else min(s['min'],value)
        s['max']=value if s['max'] is None else max(s['max'],value)
    records=0
    for part in parts:
        with (root/part['file']).open('rb') as handle:
            while True:
                line=handle.readline(65537)
                if not line: break
                if len(line)>65536 or not line.endswith(b'\n'): raise ValueError('Incomplete or oversized record')
                r=json.loads(line);records+=1
                if r['kind']=='quote':
                    v=r['venue']
                    if v not in ('spot','usdm'): raise ValueError('Unexpected venue')
                    for key in ('receipt_monotonic_ns','receipt_wall_ns'):
                        if type(r[key]) is not int or r[key]<0: raise ValueError('Invalid receipt timestamp')
                    d=dict(s=r['symbol'],u=r['update_id'],b=r['bid'],a=r['ask'],B=r['bid_size'],A=r['ask_size'])
                    if v=='usdm': d['e']='bookTicker'
                    for src,dst in (('source_event_ms','E'),('source_transaction_ms','T')):
                        if r[src] is not None: d[dst]=r[src]
                    checked=quote(json.dumps(d),v,protocol['symbol'],r['receipt_monotonic_ns'],r['receipt_wall_ns'])
                    if checked!=r: raise ValueError('Invalid normalized quote')
                    if v in latest and (r['update_id']<=latest[v]['update_id'] or
                            r['receipt_monotonic_ns']<latest[v]['receipt_monotonic_ns']):
                        raise ValueError('Quote ordering violation')
                    latest[v]=r;counts[v+'_quotes']+=1;pending=True
                elif r['kind']=='receipt_pair':
                    t=r['paired_monotonic_ns']
                    if type(t) is not int or t<last_pair_time or not pending:
                        raise ValueError('Invalid pair ordering')
                    expected=pair(latest,t)
                    if expected is None or r!=expected: raise ValueError('Pair differs from latest fresh quotes')
                    for v in ('spot','usdm'):
                        if last_pair.get(v)==r[v]['update_id']: reuse[v]+=1
                        last_pair[v]=r[v]['update_id']
                        observe(v+'_age',r['ages_ns'][v])
                    observe('skew',r['receipt_skew_ns'])
                    last_pair_time=t;pending=False;counts['receipt_pairs']+=1
                else: raise ValueError('Unknown record kind')
                if records%10000==0: print(f'[basis-audit] records={records:,}',flush=True)
    counts['unpaired_updates']=counts['spot_quotes']+counts['usdm_quotes']-counts['receipt_pairs']
    if not counts['receipt_pairs'] or dict(counts)!=summary['counts']:
        raise ValueError('Replayed counts do not match summary')
    if any(sha256(root/p)!=h for p,h in hashes.items()): raise ValueError('Capture changed during replay')
    return dict(approved=False,integrity_passed=True,pair_replay_passed=True,records=records,
        counts=dict(counts),pairs_reusing_previous_pair_quote={v:reuse[v] for v in ('spot','usdm')},
        receipt_timing_ms={k:dict(count=s['count'],mean=s['sum']/s['count']/1e6,
            min=s['min']/1e6,max=s['max']/1e6) for k,s in stats.items()},
        source_hashes=hashes,runner_sha256=sha256(Path(__file__)),
        replay_helpers_sha256=sha256(Path(__file__).with_name('record_basis_quotes.py')),
        limitations=['Checks local saved consistency, not exchange completeness or authenticity.',
            'Reuses recorder quote/pair validators; not an independent implementation.',
            'No source synchronization, RTT, executable edge, fill, fee, funding or profitability claim.',
            'Unpaired updates lack pairing timestamps, so their freshness rejection cannot be independently replayed.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Use a new output path')
    r=audit(a.capture);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({k:v for k,v in r.items() if k!='source_hashes'},indent=2))


if __name__=='__main__': main()
