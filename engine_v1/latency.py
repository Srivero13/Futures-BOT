"""Local endpoint timing. REST RTT is not exchange order execution latency."""
import argparse
import json
import math
from pathlib import Path
import time
from urllib.request import urlopen


def percentile(values, q):
    if not values: return None
    return sorted(values)[max(0, math.ceil(q*len(values))-1)]


def policy(samples, failures, attempts):
    p50=percentile(samples,.5);p95=percentile(samples,.95);p99=percentile(samples,.99)
    ready=len(samples)>=30 and failures/max(1,attempts)<=.05 and p99 is not None and p99<=1000
    return {'successes':len(samples),'attempts':attempts,'failures':failures,
        'p50_ms':p50,'p95_ms':p95,'p99_ms':p99,
        'eligible_for_paper_stream':ready,
        'quote_deadline_ms':min(1000,max(250,math.ceil(3*p99))) if p99 else 250,
        'minimum_decision_spacing_ms':max(100,math.ceil(2*p95)) if p95 else 1000,
        'minimum_horizon_ms':max(60000,math.ceil(20*p99)) if p99 else 300000,
        'rule':'Engineering heuristic, not economically optimized. Requires >=30 successes, <=5% failures, p99<=1000ms.'}


def probe(samples=30,timeout=2,location='unknown'):
    if not 1<=samples<=1000 or not 0<timeout<=30: raise ValueError('Invalid sample/timeout')
    results={};offsets=[]
    for label,path in [('server_time','/api/v3/time'),('quote','/api/v3/ticker/bookTicker?symbol=BTCUSDT')]:
        measurements=[];raw=[];failures=0
        for i in range(samples):
            start=time.perf_counter_ns();wall=time.time()*1000
            try:
                with urlopen('https://api.binance.com'+path,timeout=timeout) as response:
                    data=json.load(response)
                elapsed=(time.perf_counter_ns()-start)/1e6
                if label=='server_time':
                    if 'serverTime' not in data: raise ValueError('Missing server time')
                    offsets.append({'offset_ms':data['serverTime']-(wall+elapsed/2),'uncertainty_ms':elapsed/2})
                elif not all(k in data for k in ('bidPrice','askPrice')): raise ValueError('Missing quote')
                measurements.append(elapsed);raw.append({'rtt_ms':elapsed,'ok':True})
            except Exception as exc:
                failures+=1;raw.append({'rtt_ms':(time.perf_counter_ns()-start)/1e6,'ok':False,'error':type(exc).__name__})
            # Low request rate; includes new HTTP connections, DNS/TLS/proxy overhead.
            time.sleep(.05)
        results[label]={**policy(measurements,failures,samples),'samples':raw}
        print(label,results[label]['successes'],'/',samples,'samples',flush=True)
    best=min(offsets,key=lambda x:x['uncertainty_ms']) if offsets else None
    return {'schema':1,'created_at_ms':int(time.time()*1000),'location':location,
        'measurement':'REST response RTT via urllib (DNS/TLS/proxy included), NOT order acknowledgments or fills',
        'endpoints':results,'clock_estimate':best,
        'note':'Re-run on the actual ENTEL PC. Public endpoints alone cannot certify order latency.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--samples',type=int,default=30);p.add_argument('--timeout',type=float,default=2)
    p.add_argument('--location',default='user-pc');p.add_argument('--output',default='data/latency-local.json');a=p.parse_args()
    result=probe(a.samples,a.timeout,a.location);dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2));print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk!='samples'} for k,v in result['endpoints'].items()},indent=2))
if __name__=='__main__':main()
