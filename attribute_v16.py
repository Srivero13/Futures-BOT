"""Attribute saved reversal executions to reference-price movement and costs."""
import argparse
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import sys

from engine_v1.dataset import candles, sha256
from engine_v1.operations import atomic_json
from train_v15 import timestamp

D=lambda v:Decimal(str(v))


def finite(value):
    v=D(value)
    if not v.is_finite():raise ValueError('Non-finite monetary value')
    return v


def attribute_trade(trade,prices,costs):
    with localcontext() as ctx:
        ctx.prec=50
        decision,entry,exit_=(trade[k] for k in ('decision_ms','entry_ms','exit_ms'))
        if any(type(t) is not int or t%60000 for t in (decision,entry,exit_)) or not decision<=entry<exit_:
            raise ValueError('Invalid trade timestamps')
        signal,op,close=(finite(prices[t]) for t in (decision,entry,exit_))
        qty=finite(trade['quantity'])
        if min(signal,op,close,qty)<=0:raise ValueError('Prices and quantity must be positive')
        fee=finite(costs['fee_bps'])/10000
        impact=(finite(costs['spread_bps'])/2+finite(costs['slippage_bps']))/10000
        if not 0<=fee<1 or not 0<=impact<1:raise ValueError('Invalid cost rates')
        buy=op*(1+impact);sell=close*(1-impact)
        fees=qty*(buy+sell)*fee
        friction=qty*((buy-op)+(close-sell))
        gross=qty*(close-op);net=gross-fees-friction
        expected={'entry_price':buy,'exit_price':sell,'fees':fees,'spread_slippage_cost':friction,'net_pnl':net}
        for name,value in expected.items():
            if abs(finite(trade[name])-value)>D('1e-18'):
                raise ValueError(f'Saved trade does not reconcile: {name}')
        return {'decision_ms':decision,'entry_ms':entry,'exit_ms':exit_,
            'signal_reference_open':str(signal),'entry_reference_open':str(op),'exit_reference_open':str(close),
            'quantity':str(qty),'delay_price_change_same_quantity':str(qty*(op-signal)),
            'holding_gross_pnl':str(gross),'fees':str(fees),'spread_slippage_cost':str(friction),'net_pnl':str(net),
            'delay_log_bps':math.log(float(op/signal))*10000,
            'holding_log_bps':math.log(float(close/op))*10000,
            'signal_to_exit_log_bps':math.log(float(close/signal))*10000}


def summarize(rows):
    with localcontext() as ctx:
        ctx.prec=50
        sums={name:str(sum((D(r[name]) for r in rows),D(0))) for name in
              ('delay_price_change_same_quantity','holding_gross_pnl','fees','spread_slippage_cost','net_pnl')}
    return {'trades':len(rows),**sums,
        'positive_delay_moves':sum(r['delay_log_bps']>0 for r in rows),
        'positive_holding_moves':sum(r['holding_log_bps']>0 for r in rows),
        'mean_delay_log_bps':sum(r['delay_log_bps'] for r in rows)/len(rows) if rows else None,
        'mean_holding_log_bps':sum(r['holding_log_bps'] for r in rows)/len(rows) if rows else None}


def run(report_path,paths,output):
    report_path,output=Path(report_path),Path(output)
    if output.exists():raise ValueError('Output exists; choose a new filename')
    report_hash=sha256(report_path)
    source=json.loads(report_path.read_text())
    protocol=source['protocol'];reserve=timestamp(protocol['reserve_from'])
    paths=[Path(p).resolve() for p in paths]
    if not paths or len(set(paths))!=len(paths):raise ValueError('Supply unique chronological shards')
    expected=protocol['sources']
    if len(paths)!=len(expected):raise ValueError('Use the same source shards as the saved experiment')
    sources=[]
    print('[attribution] verifying report and source checksums',flush=True)
    for path,original in zip(paths,expected):
        digest=sha256(path)
        if digest!=original['sha256']:raise ValueError(f'Source checksum differs from experiment: {path.name}')
        meta=json.loads(path.with_suffix('.json').read_text())
        if (meta.get('sha256'),meta.get('symbol'),meta.get('venue'),meta.get('timeframe_ms'))!=(digest,protocol['symbol'],'binance',60000):
            raise ValueError('Source provenance mismatch')
        if type(meta.get('last_open_ms')) is not int or meta['last_open_ms']>=reserve:
            raise ValueError('Source reaches reserved dates or lacks range metadata')
        sources.append({'file':str(path),'sha256':digest})
    required=set();seen=set()
    for fold in source['folds']:
        start,end=timestamp(fold['test_start']),timestamp(fold['test_end'])
        if not start<end<=reserve:raise ValueError('Invalid fold boundaries')
        if fold['assumptions']!=protocol['costs']:raise ValueError('Fold and protocol costs differ')
        if len(fold['trades'])!=fold['summary']['closed_trades']:raise ValueError('Trade count mismatch')
        for t in fold['trades']:
            times=tuple(t[k] for k in ('decision_ms','entry_ms','exit_ms'))
            if any(type(v) is not int or v%60000 for v in times) or not start<=times[0]<=times[1]<times[2]<end:
                raise ValueError('Trade outside development interval')
            if times in seen:raise ValueError('Duplicate trade')
            if times[1]-times[0]!=protocol['costs']['delay_bars']*60000 or times[2]-times[1]!=protocol['horizon_minutes']*60000:
                raise ValueError('Trade timing differs from protocol')
            seen.add(times);required.update(times)
    prices={}
    if required:
        last=max(required)
        for i,row in enumerate(candles(paths),1):
            ts=row['timestamp']
            if ts>last:break
            if ts in required:prices[ts]=row['open']
            if i%262144==0:print(f'[attribution] scanned {i:,} candles; matched {len(prices)}/{len(required)} timestamps',flush=True)
        if len(prices)!=len(required):raise ValueError('Missing reference opens; attribution cannot be completed')
    all_rows=[];monthly=[]
    for fold in source['folds']:
        rows=[attribute_trade(t,prices,protocol['costs']) for t in fold['trades']]
        summary=summarize(rows)
        for name in ('net_pnl','fees','spread_slippage_cost'):
            if abs(D(summary[name])-finite(fold['summary'][name]))>D('1e-18'):
                raise ValueError(f'Monthly {name} does not reconcile')
        monthly.append({'month':fold['test_start'][:7],**summary})
        all_rows.extend(rows)
    total=summarize(all_rows)
    if total['trades']!=source['summary']['closed_trades'] or abs(D(total['net_pnl'])-finite(source['summary']['sum_independent_month_net_pnl']))>D('1e-18'):
        raise ValueError('Aggregate does not reconcile')
    if sha256(report_path)!=report_hash or any(sha256(p)!=s['sha256'] for p,s in zip(paths,sources)):
        raise ValueError('Inputs changed during attribution')
    result={'approved':False,'summary':total,'monthly':monthly,'trades':all_rows,
        'spec':{'report_sha256':report_hash,'sources':sources,'reserve_from':protocol['reserve_from'],
                'runner_sha256':sha256(Path(__file__))},
        'limitations':['Attribution of executed trades only; not a new strategy backtest or causal proof of latency effects.',
          'Signal reference is the minute open at the decision boundary, not an executable quote.',
          'Positive delay movement means price rose before the simulated entry; it is not realized P&L.',
          'Delay amount holds executed quantity and exit fixed; an earlier-entry strategy would change sizing, exit timing and trade availability.',
          'One-minute delay is a scenario assumption, not measured network RTT or evidence for a hardware upgrade.',
          'Gross holding P&L minus fees and spread/slippage reconciles to saved net P&L. Do not subtract costs twice.',
          'Monthly cash resets remain; totals are not compounded portfolio returns. Reserved data excluded.']}
    atomic_json(output,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--files',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try:
        r=run(a.report,a.files,a.output)
        print(json.dumps({'summary':r['summary'],'monthly':r['monthly']},indent=2))
        print(f'Completed: {a.output}; attribution only, unapproved.')
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f'Attribution stopped: {error}',file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('Interrupted; no complete output published.',file=sys.stderr);return 130


if __name__=='__main__':raise SystemExit(main())
