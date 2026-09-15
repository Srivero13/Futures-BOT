"""Read-only Binance WebSocket coordinator with bounded telemetry and paper controls."""
import argparse
from collections import Counter,deque
from contextlib import nullcontext
import json
import math
from pathlib import Path
import random
import time
from urllib.request import urlopen
import websocket
from .core import Portfolio,Quote,Rules,dec,break_even_bps
from .latency import percentile,policy as timing_policy
from .model import RidgeModel,feature_matrix
from .operations import atomic_json,process_lock
ROOT=Path(__file__).resolve().parent.parent


def rules_from_exchange(info):
    if info.get('status','TRADING')!='TRADING' or info.get('isSpotTradingAllowed',True) is not True:
        raise ValueError('Symbol is not eligible for spot paper entries')
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
        if k['x'] is not True:return False
        ts=int(k['t']);last=self.last_closed.get(s)
        if ts<0 or ts%60000:raise ValueError('Invalid candle timestamp')
        if last is not None and ts<=last:return False
        values={v:dec(k[v]) for v in ('o','h','l','c','v')}
        if min(values[v] for v in ('o','h','l','c'))<=0 or values['v']<0 or values['l']>min(values['o'],values['c']) or values['h']<max(values['o'],values['c']):
            raise ValueError('Invalid closed OHLCV candle')
        if last is not None and ts-last!=60000:
            self.rows[s]=deque(maxlen=21);self.healthy.discard(s)
        rows=self.rows.setdefault(s,deque(maxlen=21))
        rows.append({'timestamp':ts,'open':k['o'],'high':k['h'],'low':k['l'],'close':k['c'],'volume':k['v']})
        self.last_closed[s]=ts
        if len(rows)==21:self.healthy.add(s)
        return True


def load_profile(path,now_ms):
    profile=json.loads(Path(path).read_text())
    age=now_ms-profile['created_at_ms']
    if not math.isfinite(age) or not 0<=age<=86400000:raise ValueError('Latency profile expired/future: probe again on this PC')
    if profile['location']!='user-pc':raise ValueError('A local user-pc profile is required')
    for name in ('quote','server_time'):
        raw=profile['endpoints'][name]['samples']
        if not raw or any(type(s.get('ok')) is not bool for s in raw):raise ValueError('Invalid raw timing samples')
        successes=[s['rtt_ms'] for s in raw if s['ok']]
        derived=timing_policy(successes,len(raw)-len(successes),len(raw))
        if not derived['eligible_for_paper_stream']:raise ValueError('Local latency profile did not pass')
        # Never trust a hand-edited eligible flag or deadline.
        profile['endpoints'][name]={**derived,'samples':raw}
    clock=profile.get('clock_estimate')
    if not clock or not all(math.isfinite(clock[k]) for k in ('offset_ms','uncertainty_ms')) or not 0<=clock['uncertainty_ms']<=250:
        raise ValueError('Clock uncertainty too high or invalid')
    return profile


def entry_gate(model,feed,symbol,now,profile,paused=False,clock_ok=True):
    if paused:return 'operator_paused'
    if not clock_ok:return 'clock_jump'
    if not 0<=now-profile['created_at_ms']<=86400000:return 'profile_expired'
    if not model.approved:return 'model_unapproved'
    if not 0<=now-model.calibration_end_ms<=7*86400000:return 'model_expired'
    if model.horizon_bars*60000<profile['endpoints']['quote']['minimum_horizon_ms']:return 'horizon_too_short'
    if symbol not in feed.healthy:return 'candle_warmup'
    if not 0<=now-feed.last_closed[symbol]-60000<=90000:return 'stale_candles'
    q=feed.quotes.get(symbol)
    if q is None or not 0<=now-q.timestamp_ms<=profile['endpoints']['quote']['quote_deadline_ms']:return 'stale_quote'
    return 'ready'


def stream(duration=60,profile_path=None,observe=True,config_path=None,health_path=None):
    if duration<0:raise ValueError('Duration must be nonnegative; zero runs until interrupted')
    cfg=json.loads(Path(config_path or ROOT/'configs/v11-paper.json').read_text())
    if cfg['mode']!='paper':raise ValueError('Only paper mode is implemented')
    profile=load_profile(profile_path,int(time.time()*1000)) if not observe else None
    policy=profile['endpoints']['quote'] if profile else {'quote_deadline_ms':1000,'minimum_decision_spacing_ms':1000}
    accounts=cfg['accounts'];symbols={a['symbol'] for a in accounts}
    if not symbols or any(not s.isalnum() for s in symbols):raise ValueError('Invalid symbols')
    model_dir=ROOT/cfg['model_directory']
    models={s:RidgeModel.load(model_dir/f'{s}-v1.json') for s in symbols} if not observe else {}
    for a in accounts:
        if not observe:
            if models[a['symbol']].symbol!=a['symbol']:raise ValueError('Model symbol mismatch')
            a['horizon_ms']=models[a['symbol']].horizon_bars*60000
    db_path=ROOT/cfg['database'];db_path.parent.mkdir(parents=True,exist_ok=True)
    health_path=Path(health_path or ROOT/('data/observe-health.json' if observe else 'data/health.json'))
    feed=FeedState();rules={};events=0;reconnects=0;start=time.monotonic();wall_start=time.time()*1000
    last_decision=0.;last_health=-1e9;last_prune=0.;last_received=None;clock_ok=True;engine=None
    gaps=deque(maxlen=4096);lags=deque(maxlen=4096);costs=deque(maxlen=4096);errors=Counter();gates={};features={}
    def remaining():return max(0.,duration-(time.monotonic()-start)) if duration else float('inf')
    def health(running=True):
        now=int(time.time()*1000)
        ages={s:now-q.timestamp_ms for s,q in feed.quotes.items()}
        atomic_json(health_path,{'version':'1.1.0','running':running,'observe_only':observe,'timestamp_ms':now,
            'messages':events,'reconnects':reconnects,'errors':dict(errors),'clock_ok':clock_ok,
            'quote_age_ms':ages,'warm_candles':{s:len(r) for s,r in feed.rows.items()},'entry_gates':gates,
            'accounts':engine.states() if engine else [],'valuation_note':'last_equity is a historical mark, not a current executable balance',
            'decision_compute_p99_ms':percentile(costs,.99),'sample_window':4096})
    lock=process_lock(str(db_path)+'.lock') if not observe else nullcontext()
    with lock:
        try:
            if not observe:
                engine=Portfolio(db_path,accounts,max_age_ms=policy['quote_deadline_ms'],**cfg['risk'])
                with urlopen('https://api.binance.com/api/v3/exchangeInfo',timeout=5) as r:info=json.load(r)
                rules={s['symbol']:rules_from_exchange(s) for s in info['symbols'] if s['symbol'] in symbols}
                if set(rules)!=symbols:raise ValueError('Missing trading rules')
            names='/'.join(f'{s.lower()}@bookTicker/{s.lower()}@kline_1m' for s in sorted(symbols))
            url='wss://stream.binance.com:443/stream?streams='+names
            failures=0
            while remaining()>0:
                sock=None;feed.reset_quotes();features.clear();last_received=None;gates={a['id']:'feed_disconnected' for a in accounts}
                try:
                    health();sock=websocket.create_connection(url,timeout=min(5,remaining()))
                    connection_start=time.monotonic()
                    while remaining()>0:
                        sock.settimeout(min(5,remaining()))
                        raw=sock.recv();mono=time.monotonic();now=int(time.time()*1000)
                        if not raw:raise ConnectionError('WebSocket closed')
                        if abs((now-wall_start)-(mono-start)*1000)>250:
                            clock_ok=False;feed.reset_quotes();features.clear()
                        if mono-last_health>=5:health();last_health=mono
                        message=json.loads(raw);d=message.get('data',message)
                        if d.get('e')=='serverShutdown':raise ConnectionError('Scheduled shutdown')
                        if d.get('s') not in symbols:continue
                        events+=1
                        if mono-connection_start>20:failures=0
                        if last_received is not None:gaps.append((mono-last_received)*1000)
                        last_received=mono
                        if 'u' in d and 'b' in d:feed.accept_book(d,now)
                        elif d.get('e')=='kline':
                            if profile:
                                clock=profile['clock_estimate'];lag=now+clock['offset_ms']-d['E'];lags.append(lag)
                                if lag>policy['quote_deadline_ms']+clock['uncertainty_ms'] or lag < -clock['uncertainty_ms']:
                                    feed.healthy.discard(d['s']);continue
                            if feed.accept_kline(d):features.pop(d['s'],None)
                        paused=(ROOT/'PAUSE').exists();flatten=(ROOT/'FLATTEN').exists()
                        if not observe and (mono-last_decision)*1000>=policy['minimum_decision_spacing_ms']:
                            t0=time.perf_counter_ns();decisions={}
                            for a in accounts:
                                s=a['symbol'];m=models[s]
                                gate=entry_gate(m,feed,s,now,profile,paused or flatten,clock_ok);gates[a['id']]=gate
                                if gate=='ready':
                                    if s not in features:features[s]=feature_matrix(list(feed.rows[s]))[-1]
                                    decisions[a['id']]=m.decision(features[s],break_even_bps(feed.quotes[s],cfg['risk']['fee_bps'],cfg['risk']['slip_bps']))
                            outputs=engine.process(feed.quotes,decisions,now,event_id=f'ws:{time.time_ns()}',rules=rules,
                                cooldown_ms=cfg['cooldown_ms'],max_entries_day=cfg['max_entries_day'],allow_entries=not(paused or flatten) and clock_ok,force_exit=flatten)
                            costs.append((time.perf_counter_ns()-t0)/1e6);last_decision=mono
                            for output in outputs:
                                if output['action'] in ('BUY','SELL'):print(json.dumps(output),flush=True)
                            if mono-last_prune>=300:engine.prune(now);last_prune=mono
                except (OSError,ValueError,KeyError,TypeError,websocket.WebSocketException) as exc:
                    errors[type(exc).__name__]+=1;reconnects+=1;failures+=1;feed.reset_quotes();features.clear()
                    gates={a['id']:'feed_disconnected' for a in accounts};health()
                    delay=min(30,2**min(failures,5))*(.8+.2*random.random())
                    # Refresh heartbeat while waiting; empty quotes expose the outage.
                    deadline=time.monotonic()+min(remaining(),delay)
                    while time.monotonic()<deadline:
                        time.sleep(max(0,min(1,deadline-time.monotonic())));health()
                finally:
                    if sock is not None:sock.close()
        except KeyboardInterrupt:pass
        finally:
            health(False)
            if engine is not None:engine.close()
    return {'version':'1.1.0','location':'current-runtime','observe_only':observe,'messages':events,'reconnects':reconnects,
        'errors':dict(errors),'duration_seconds':time.monotonic()-start,'clock_ok':clock_ok,
        'interarrival_p95_ms':percentile(gaps,.95),'kline_lag_p95_ms':percentile(lags,.95),
        'decision_compute_p99_ms':percentile(costs,.99),'sample_window':4096,
        'note':'Bounded recent samples. Interarrival is not RTT. BookTicker lacks source event time. No real orders.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=int,default=60);p.add_argument('--profile')
    p.add_argument('--paper',action='store_true');p.add_argument('--config');p.add_argument('--health')
    p.add_argument('--output',default='data/stream-probe.json');a=p.parse_args()
    if a.paper and not a.profile:p.error('--paper requires --profile')
    result=stream(a.seconds,a.profile,not a.paper,a.config,a.health);atomic_json(a.output,result);print(json.dumps(result,indent=2))
if __name__=='__main__':main()
