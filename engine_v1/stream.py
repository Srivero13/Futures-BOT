"""Read-only Binance stream -> shared paper engine. Never signs or sends orders."""
import argparse
from collections import deque
import json
from pathlib import Path
import time
from urllib.request import urlopen
import websocket
from .core import Portfolio,Quote,Rules,dec,break_even_bps
from .model import RidgeModel,feature_matrix
ROOT=Path(__file__).resolve().parent.parent


def rules_from_exchange(info):
    filters={f['filterType']:f for f in info['filters']}
    lot=filters.get('MARKET_LOT_SIZE',{})
    if dec(lot.get('stepSize','0'))<=0:lot=filters['LOT_SIZE']
    nominal=filters.get('NOTIONAL',filters.get('MIN_NOTIONAL',{}))
    return Rules(lot['stepSize'],lot['minQty'],lot['maxQty'],nominal.get('minNotional','5'),nominal.get('maxNotional','1000000000')).validate()


class FeedState:
    def __init__(self):self.quotes={};self.rows={};self.last_closed={};self.healthy=set()
    def reset_quotes(self):self.quotes.clear();self.healthy.clear()
    def accept_book(self,data,now_ms):
        symbol=data['s'];seq=int(data['u']);old=self.quotes.get(symbol)
        if old and seq<=old.sequence:return False
        q=Quote(symbol,dec(data['b']),dec(data['a']),dec(data['B']),dec(data['A']),now_ms,seq).validate()
        self.quotes[symbol]=q;return True
    def accept_kline(self,data):
        k=data['k'];s=data['s']
        if not k['x']:return False
        ts=int(k['t']);last=self.last_closed.get(s)
        if last is not None and ts<=last:return False
        if last is not None and ts-last!=60000:
            self.rows[s]=deque(maxlen=21);self.healthy.discard(s)
        rows=self.rows.setdefault(s,deque(maxlen=21))
        rows.append({'timestamp':ts,'open':k['o'],'high':k['h'],'low':k['l'],'close':k['c'],'volume':k['v']})
        self.last_closed[s]=ts
        if len(rows)==21:self.healthy.add(s)
        return True


def load_profile(path,now_ms):
    profile=json.loads(Path(path).read_text());policy=profile['endpoints']['quote']
    age=now_ms-profile['created_at_ms']
    if not 0<=age<=86400000:raise ValueError('Latency profile expired/future: probe again on this PC')
    if profile['location']!='user-pc' or not policy['eligible_for_paper_stream']:raise ValueError('A passing local user-pc latency profile is required')
    if not profile['endpoints']['server_time']['eligible_for_paper_stream']:raise ValueError('Clock endpoint calibration failed')
    clock=profile.get('clock_estimate')
    if not clock or clock['uncertainty_ms']>250:raise ValueError('Clock uncertainty too high')
    return profile


def stream(duration=60,profile_path=None,observe=True):
    if duration<=0:raise ValueError('Positive duration required')
    profile=load_profile(profile_path,int(time.time()*1000)) if not observe else None
    policy=profile['endpoints']['quote'] if profile else {'quote_deadline_ms':1000,'minimum_decision_spacing_ms':1000,'minimum_horizon_ms':60000}
    accounts=[{'id':'binance-a','symbol':'BTCUSDT','capital':'1000','notional':'100'},
              {'id':'binance-b','symbol':'ETHUSDT','capital':'1000','notional':'100'}]
    models={s:RidgeModel.load(ROOT/'models'/f'{s}-v1.json') for s in ('BTCUSDT','ETHUSDT')}
    for a in accounts:a['horizon_ms']=models[a['symbol']].horizon_bars*60000
    (ROOT/'data').mkdir(exist_ok=True)
    engine=Portfolio(':memory:' if observe else ROOT/'data/v1-paper.sqlite3',accounts,max_age_ms=policy['quote_deadline_ms'])
    feed=FeedState();rules={};events=0;reconnects=0;start=time.monotonic();last_decision=0.;gaps=[];last_received=None
    received_lags=[];errors=[];decision_costs=[]
    # This endpoint is read-only. Rules must be fetched before paper entries.
    if not observe:
        with urlopen('https://api.binance.com/api/v3/exchangeInfo',timeout=5) as r:info=json.load(r)
        rules={s['symbol']:rules_from_exchange(s) for s in info['symbols'] if s['symbol'] in models}
        if set(rules)!=set(models):raise ValueError('Missing trading rules')
    names='/'.join(f'{s.lower()}@bookTicker/{s.lower()}@kline_1m' for s in models)
    url='wss://stream.binance.com:443/stream?streams='+names
    try:
        while time.monotonic()-start<duration:
            sock=None;feed.reset_quotes()
            try:
                sock=websocket.create_connection(url,timeout=5)
                while time.monotonic()-start<duration:
                    raw=sock.recv();recv_monotonic=time.monotonic();now=int(time.time()*1000)
                    if not raw:raise ConnectionError('WebSocket closed')
                    message=json.loads(raw);d=message.get('data',message)
                    if d.get('e')=='serverShutdown':raise ConnectionError('Scheduled server shutdown')
                    events+=1
                    if last_received is not None:gaps.append((recv_monotonic-last_received)*1000)
                    last_received=recv_monotonic
                    if 'u' in d and 'b' in d:feed.accept_book(d,now)
                    elif d.get('e')=='kline':
                        # Kline timestamps allow lag checking; bookTicker has no E timestamp.
                        if profile:
                            clock=profile['clock_estimate'];lag=now+clock['offset_ms']-d['E'];received_lags.append(lag)
                            if lag>policy['quote_deadline_ms']+clock['uncertainty_ms'] or lag < -clock['uncertainty_ms']:
                                feed.healthy.discard(d['s']);continue
                        feed.accept_kline(d)
                    if observe or (recv_monotonic-last_decision)*1000<policy['minimum_decision_spacing_ms']:continue
                    t0=time.perf_counter_ns();decisions={}
                    for a in accounts:
                        s=a['symbol'];m=models[s];q=feed.quotes.get(s)
                        fresh_model=0<=now-m.calibration_end_ms<=7*86400000
                        fresh_candles=s in feed.healthy and 0<=now-feed.last_closed[s]-60000<=90000
                        if q and fresh_model and fresh_candles and m.approved and m.horizon_bars*60000>=policy['minimum_horizon_ms'] and now-profile['created_at_ms']<=86400000:
                            x=feature_matrix(list(feed.rows[s]))[-1]
                            decisions[a['id']]=m.decision(x,break_even_bps(q,'10','2'))
                    # Each account carries its model's horizon; fallback is only for legacy configs.
                    horizon=min(m.horizon_bars for m in models.values())*60000
                    outputs=engine.process(feed.quotes,decisions,now,event_id=f'ws:{time.time_ns()}',rules=rules,
                        horizon_ms=horizon,cooldown_ms=60000)
                    decision_costs.append((time.perf_counter_ns()-t0)/1e6);last_decision=recv_monotonic
                    for output in outputs:
                        if output['action']!='HOLD':print(json.dumps(output),flush=True)
            except (OSError,ValueError,KeyError,websocket.WebSocketException) as exc:
                errors.append(type(exc).__name__);reconnects+=1;feed.reset_quotes()
                remaining=duration-(time.monotonic()-start)
                if remaining>0:time.sleep(min(remaining,min(30,2**min(reconnects,5))))
            finally:
                if sock is not None:sock.close()
    finally:engine.close()
    from .latency import percentile
    summary={'location':'current-runtime','observe_only':observe,'messages':events,'reconnects':reconnects,
        'errors':errors,'duration_seconds':time.monotonic()-start,
        'interarrival_p95_ms':percentile(gaps,.95),'kline_lag_p95_ms':percentile(received_lags,.95),
        'decision_compute_p99_ms':percentile(decision_costs,.99),
        'note':'Interarrival is not RTT. BookTicker has no event timestamp; local receipt-age checks cannot prove exchange freshness.'}
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=60);p.add_argument('--profile')
    p.add_argument('--paper',action='store_true',help='Enable local paper decisions; requires valid local profile and promoted fresh models')
    p.add_argument('--output',default='data/stream-probe.json');a=p.parse_args()
    result=stream(a.seconds,a.profile,not a.paper);dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
