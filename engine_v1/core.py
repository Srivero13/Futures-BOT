"""Decimal accounting shared by replay and online paper. No real order path."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, getcontext
import hashlib
import json
import sqlite3
from pathlib import Path
getcontext().prec=50


def dec(value):
    if isinstance(value,(float,bool)): raise ValueError('Use decimal strings, not floats/bools')
    x=Decimal(value)
    if not x.is_finite(): raise ValueError('Non-finite decimal')
    return x


def floor_step(value,step):
    if step<=0: raise ValueError('Invalid quantity step')
    return (value/step).to_integral_value(rounding=ROUND_DOWN)*step

@dataclass(frozen=True)
class Quote:
    symbol:str
    bid:Decimal
    ask:Decimal
    bid_qty:Decimal
    ask_qty:Decimal
    timestamp_ms:int
    sequence:int

    def validate(self):
        if any(not isinstance(x,Decimal) or not x.is_finite() or x<=0 for x in (self.bid,self.ask,self.bid_qty,self.ask_qty)):
            raise ValueError('Invalid quote')
        if self.ask<self.bid or self.timestamp_ms<0 or self.sequence<0: raise ValueError('Crossed/invalid quote')
        return self

    @property
    def spread_bps(self): return (self.ask-self.bid)/((self.ask+self.bid)/2)*10000

    @property
    def microprice(self):
        return (self.ask*self.bid_qty+self.bid*self.ask_qty)/(self.bid_qty+self.ask_qty)

@dataclass(frozen=True)
class Rules:
    step:str='0.000001'
    min_qty:str='0.000001'
    max_qty:str='1000000'
    min_notional:str='5'
    max_notional:str='1000000000'
    def validate(self):
        values=[dec(x) for x in (self.step,self.min_qty,self.max_qty,self.min_notional,self.max_notional)]
        if min(values)<=0 or values[1]>values[2] or values[3]>values[4]: raise ValueError('Invalid rules')
        return self


def break_even_bps(quote,fee_bps,slip_bps):
    f=dec(fee_bps)/10000;s=dec(slip_bps)/10000
    if not 0<=f<1 or not 0<=s<1: raise ValueError('Invalid costs')
    # Required future bid / current bid - 1, fees paid in quote currency.
    return (quote.ask*(1+s)*(1+f)/(quote.bid*(1-s)*(1-f))-1)*10000


class Portfolio:
    def __init__(self,path,accounts,*,fee_bps='10',slip_bps='2',global_cap='200',
                 drawdown='0.05',daily_loss='0.02',max_age_ms=1000,max_spread_bps='20'):
        self.config={'accounts':accounts,'fee_bps':fee_bps,'slip_bps':slip_bps,'global_cap':global_cap,
            'drawdown':drawdown,'daily_loss':daily_loss,'max_age_ms':max_age_ms,'max_spread_bps':max_spread_bps}
        self.fee=dec(fee_bps)/10000;self.slip=dec(slip_bps)/10000;self.cap=dec(global_cap)
        self.dd=dec(drawdown);self.daily=dec(daily_loss);self.max_age=max_age_ms;self.spread=dec(max_spread_bps)
        if not (0<=self.fee<1 and 0<=self.slip<1 and self.cap>0 and 0<self.dd<1 and 0<self.daily<1 and max_age_ms>0 and self.spread>0):raise ValueError('Invalid risk config')
        if not accounts or len({a['id'] for a in accounts})!=len(accounts):raise ValueError('Unique accounts required')
        for a in accounts:
            if not a['symbol'].isalnum() or dec(a['capital'])<=0 or not 0<dec(a['notional'])<=dec(a['capital']):raise ValueError('Invalid account')
            if 'horizon_ms' in a and (type(a['horizon_ms']) is not int or a['horizon_ms']<=0):raise ValueError('Invalid account horizon')
        self.db=sqlite3.connect(path,timeout=10,isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL');self.db.execute('PRAGMA busy_timeout=10000')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY, fingerprint TEXT);
        CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS risk (id INTEGER PRIMARY KEY, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS processed (account TEXT, event TEXT, PRIMARY KEY(account,event));
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp_ms INTEGER, account TEXT, payload TEXT);
        ''')
        fingerprint=hashlib.sha256(json.dumps(self.config,sort_keys=True).encode()).hexdigest()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT fingerprint FROM config WHERE id=1').fetchone()
            if row and row[0]!=fingerprint:raise ValueError('Configuration mismatch: use a new database')
            self.db.execute('INSERT OR IGNORE INTO config VALUES(1,?)',(fingerprint,))
            total=sum((dec(a['capital']) for a in accounts),dec(0))
            for a in accounts:
                state={**a,'cash':a['capital'],'qty':'0','basis':'0','realized':'0','fees':'0','entry_ms':0,
                       'last_exit_ms':-10**15,'entries':0,'day':-1,'last_sequence':-1,
                       'peak':a['capital'],'day_start':a['capital'],'halted':False,'day_halted':False}
                self.db.execute('INSERT OR IGNORE INTO accounts VALUES(?,?)',(a['id'],json.dumps(state)))
            self.db.execute('INSERT OR IGNORE INTO risk VALUES(1,?)',(json.dumps({'peak':str(total),'day_start':str(total),'day':-1,'halted':False,'day_halted':False}),))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');self.db.close();raise

    def states(self):return [json.loads(r[0]) for r in self.db.execute('SELECT state FROM accounts ORDER BY id')]

    def process(self,quotes,decisions,now_ms,*,event_id,rules=None,horizon_ms=300000,cooldown_ms=60000,max_entries_day=12):
        if horizon_ms<=0 or cooldown_ms<0 or max_entries_day<0:raise ValueError('Invalid timing')
        for q in quotes.values():q.validate()
        rules=rules or {}
        self.db.execute('BEGIN IMMEDIATE')
        try:
            states=self.states();risk=json.loads(self.db.execute('SELECT state FROM risk WHERE id=1').fetchone()[0])
            fresh=lambda q: q is not None and 0<=now_ms-q.timestamp_ms<=self.max_age
            # Fail closed if any held symbol lacks a fresh valuation. No guessed liquidation fills.
            if any(dec(a['qty']) and not fresh(quotes.get(a['symbol'])) for a in states):
                self.db.execute('COMMIT');return [{'action':'STALE_PORTFOLIO','timestamp_ms':now_ms}]
            def equity(a):
                q=quotes.get(a['symbol']);v=dec(a['qty'])*q.bid*(1-self.slip)*(1-self.fee) if q else dec(0)
                return dec(a['cash'])+v
            eq=sum((equity(a) for a in states),dec(0));day=now_ms//86400000
            if day!=risk['day']:
                risk.update(day=day,day_start=str(eq),day_halted=False)
            risk['peak']=str(max(dec(risk['peak']),eq))
            if eq<=dec(risk['peak'])*(1-self.dd):risk['halted']=True
            if eq<=dec(risk['day_start'])*(1-self.daily):risk['day_halted']=True
            blocked=risk['halted'] or risk['day_halted'];result=[];liquidity={}
            for a in states:
                q=quotes.get(a['symbol'])
                if not fresh(q):continue
                key=str(event_id)
                if self.db.execute('SELECT 1 FROM processed WHERE account=? AND event=?',(a['id'],key)).fetchone():continue
                if q.sequence<a['last_sequence']:raise ValueError('Out-of-order quote')
                decision=decisions.get(a['id'],{})
                cash,qty,basis=map(dec,(a['cash'],a['qty'],a['basis']))
                if a['day']!=day:a.update(day=day,entries=0,day_start=str(equity(a)),day_halted=False)
                a['peak']=str(max(dec(a['peak']),equity(a)))
                if equity(a)<=dec(a['peak'])*(1-self.dd):a['halted']=True
                if equity(a)<=dec(a['day_start'])*(1-self.daily):a['day_halted']=True
                account_blocked=blocked or a['halted'] or a['day_halted']
                action='HOLD';price=dec(0);fee=dec(0);amount=dec(0);reason='no_edge'
                if qty and (account_blocked or now_ms-a['entry_ms']>=a.get('horizon_ms',horizon_ms) or decision.get('exit',False)):
                    price=q.bid*(1-self.slip);amount=qty
                    # Paper exits are assumed full; actual partial fills/dust require an exchange executor.
                    fee=amount*price*self.fee;proceeds=amount*price-fee
                    a['realized']=str(dec(a['realized'])+proceeds-basis)
                    cash+=proceeds;qty=dec(0);basis=dec(0);a['last_exit_ms']=now_ms
                    action='SELL';reason='risk' if account_blocked else 'horizon_or_signal'
                elif not qty and not account_blocked and decision.get('enter',False):
                    rule=rules.get(a['symbol'],Rules()).validate()
                    exposure=sum((dec(b['qty'])*quotes[b['symbol']].ask for b in states if dec(b['qty'])),dec(0))
                    room=max(dec(0),self.cap-exposure)
                    price=q.ask*(1+self.slip)
                    used=liquidity.get(a['symbol'],dec(0))
                    available=max(dec(0),q.ask_qty*dec('0.1')-used)
                    budget=min(dec(a['notional']),cash/(1+self.fee),room,dec(rule.max_notional))
                    amount=floor_step(min(budget/price,available,dec(rule.max_qty)),dec(rule.step))
                    if q.spread_bps<=self.spread and now_ms-a['last_exit_ms']>=cooldown_ms and a['entries']<max_entries_day and amount>=dec(rule.min_qty) and amount*price>=dec(rule.min_notional):
                        fee=amount*price*self.fee;basis=amount*price+fee;cash-=basis;qty=amount
                        a['entry_ms']=now_ms;a['entries']+=1;action='BUY';reason='cost_adjusted_edge';liquidity[a['symbol']]=used+amount
                    else:amount=dec(0);reason='risk_size_spread_or_cooldown'
                a.update(cash=str(cash),qty=str(qty),basis=str(basis),fees=str(dec(a['fees'])+fee),last_sequence=q.sequence)
                eq_now=sum((equity(b) for b in states),dec(0))
                risk['peak']=str(max(dec(risk['peak']),eq_now))
                if eq_now<=dec(risk['peak'])*(1-self.dd):risk['halted']=True
                if eq_now<=dec(risk['day_start'])*(1-self.daily):risk['day_halted']=True
                blocked=risk['halted'] or risk['day_halted']
                payload={'action':action,'reason':reason,'timestamp_ms':now_ms,'account':a['id'],'symbol':a['symbol'],
                    'price':str(price),'quantity':str(amount),'fee':str(fee),'cash':a['cash'],'qty':a['qty'],
                    'equity':str(equity(a)),'realized':a['realized'],'unrealized':str(equity(a)-cash-basis),
                    'microprice':str(q.microprice)}
                self.db.execute('UPDATE accounts SET state=? WHERE id=?',(json.dumps(a),a['id']))
                self.db.execute('INSERT INTO processed VALUES(?,?)',(a['id'],key))
                self.db.execute('INSERT INTO events VALUES(NULL,?,?,?)',(now_ms,a['id'],json.dumps(payload)))
                result.append(payload)
            eq_after=sum((equity(a) for a in states),dec(0));risk['peak']=str(max(dec(risk['peak']),eq_after))
            if eq_after<=dec(risk['peak'])*(1-self.dd):risk['halted']=True
            if eq_after<=dec(risk['day_start'])*(1-self.daily):risk['day_halted']=True
            self.db.execute('UPDATE risk SET state=? WHERE id=1',(json.dumps(risk),))
            self.db.execute('COMMIT');return result
        except Exception:
            self.db.execute('ROLLBACK');raise

    def close(self):self.db.close()
