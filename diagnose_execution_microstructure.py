"""Frozen-model long-only delayed-quote cost diagnostic; no orders or promotion."""
import argparse
from collections import Counter
from decimal import Decimal,localcontext
import json
import math
from pathlib import Path
import sys
import numpy as np
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from replay_market import replay
from train_microstructure import FEATURES,SETTINGS,predict

D=Decimal


def costs(entry,exit,notional=D('100')):
    """Reference top quotes; fixed adverse slippage and fees on actual notionals."""
    with localcontext() as ctx:
        ctx.prec=50
        eb,ea,ebq,eaq=entry;xb,xa,xbq,xaq=exit
        buy=ea*(1+D('0.0002'));sell=xb*(1-D('0.0002'))
        qty=notional/buy
        if qty>eaq or qty>xbq:return None
        fees=qty*(buy+sell)*D('0.001')
        gross=qty*(sell-buy);net=gross-fees
        midpoint=qty*((xb+xa)/2-(eb+ea)/2)
        return {'quantity':str(qty),'entry_price':str(buy),'exit_price':str(sell),
            'entry_notional':str(notional),'fees':str(fees),'midpoint_pnl':str(midpoint),
            'spread_slippage_cost':str(midpoint-gross),'net_pnl':str(net),
            'net_return_bps':float(net/notional*10000)}


class Diagnostic:
    def __init__(self,model):
        self.model=model;self.pending=None;self.position=None;self.last=None;self.warm=None;self.next_decision=0
        self.counts=Counter();self.trades=[]
        cuts=model['training_forecast_bucket_cuts']
        if not cuts:raise ValueError('Model has no distinct training forecast buckets')
        self.threshold=float(cuts[-1])

    def reset(self,reason):
        if self.pending:self.counts['cancelled_entry_'+reason]+=1
        if self.position:self.counts['unresolved_position_'+reason]+=1
        self.pending=None;self.position=None;self.last=None;self.warm=None;self.next_decision=0

    def accept(self,r,q):
        if r.get('receipt_wall_ns',self.model['frozen_at_wall_ns']+1)<=self.model['frozen_at_wall_ns']:
            raise ValueError('Capture must start after model freeze')
        if q is None:self.reset('boundary');return
        t=r['receipt_monotonic_ns']
        if self.last is not None and t-self.last>1_000_000_000:self.reset('gap')
        self.last=t
        if self.warm is None:self.warm=t
        if t-self.warm<1_000_000_000:return
        if self.position:
            age=t-self.position['entry_ns']
            if age<5_000_000_000:return
            position=self.position;self.position=None
            if age>5_250_000_000:self.counts['unresolved_position_late_exit']+=1
            else:
                result=costs(position['quote'],q)
                if result is None:self.counts['unresolved_position_exit_depth']+=1
                else:
                    self.trades.append({**result,'decision_ns':position['decision_ns'],'entry_ns':position['entry_ns'],
                        'exit_ns':t,'prediction_log_bps':position['prediction'],'actual_entry_delay_ms':(position['entry_ns']-position['decision_ns'])/1e6})
            return
        if self.pending:
            age=t-self.pending['decision_ns']
            if age<500_000_000:return
            pending=self.pending;self.pending=None
            if age>750_000_000:self.counts['cancelled_entry_late']+=1;return
            if D('100')/(q[1]*D('1.0002'))>q[3]:self.counts['cancelled_entry_depth']+=1;return
            self.position={**pending,'entry_ns':t,'quote':q};self.counts['entries']+=1
            return
        if t<self.next_decision:return
        self.next_decision=t+5_000_000_000;self.counts['decisions']+=1
        bid,ask,bq,aq=map(float,q);mid=(bid+ask)/2
        x=np.array([[(ask-bid)/mid*10000,(bq-aq)/(bq+aq),math.log(bq+aq)]])
        forecast=float(predict(x,self.model)[0])
        if not math.isfinite(forecast):raise ValueError('Non-finite forecast')
        if forecast>=self.threshold and forecast>0:
            self.counts['candidates']+=1
            self.pending={'decision_ns':t,'prediction':forecast}

    def summary(self):
        with localcontext() as ctx:
            ctx.prec=50
            totals={k:str(sum((D(r[k]) for r in self.trades),D(0))) for k in ('fees','midpoint_pnl','spread_slippage_cost','net_pnl')}
        unresolved=sum(v for k,v in self.counts.items() if k.startswith('unresolved_position_'))
        return {'counts':dict(self.counts),'closed_trades':len(self.trades),'unresolved_positions':unresolved,
            'complete_execution_result':False,'training_top_bucket_threshold_log_bps':self.threshold,
            'closed_trade_totals':totals,'closed_trade_win_rate':sum(D(r['net_pnl'])>0 for r in self.trades)/len(self.trades) if self.trades else None}


def run(capture,model_path,output):
    capture=Path(capture).resolve();model_path=Path(model_path);output=Path(output)
    if output.exists():raise ValueError('Output exists; choose a new directory')
    model_hash=sha256(model_path);model=json.loads(model_path.read_text())
    if model['kind']!='microstructure_research_ridge' or model['features']!=FEATURES or model['settings']!=SETTINGS or model['alpha']!=10:
        raise ValueError('Unsupported model')
    if model['runner_sha256']!=sha256(Path(__file__).parent/'train_microstructure.py'):raise ValueError('Training code changed')
    if str(capture)==model['training']['capture']:raise ValueError('Do not evaluate on development capture')
    for name,digest in model['training']['builder_code_sha256'].items():
        if sha256(Path(__file__).parent/name)!=digest:raise ValueError('Sampling code changed: '+name)
    current_protocol=json.loads((capture/'protocol.json').read_text())
    training_protocol=json.loads((Path(model['training']['capture'])/'protocol.json').read_text())
    if current_protocol['symbol']!=training_protocol['symbol']:raise ValueError('Training and evaluation symbols differ')
    output.mkdir(parents=True)
    protocol={'model_sha256':model_hash,'capture':str(capture),'entry_delay_ms':500,'holding_ms_after_entry':5000,
        'max_scheduling_lateness_ms':250,'decision_spacing_ms':5000,'notional':'100','fee_bps_per_side':10,
        'slippage_bps_per_side':2,'selection':'positive forecast in training-defined highest bucket',
        'runner_sha256':sha256(Path(__file__)),'approved':False}
    atomic_json(output/'protocol.json',protocol)
    simulator=Diagnostic(model)
    replay(capture,output/'replay-verification.json',on_quote=simulator.accept)
    simulator.reset('end')
    if sha256(model_path)!=model_hash:raise ValueError('Model changed during diagnostic')
    summary=simulator.summary()
    atomic_json(output/'report.json',{'approved':False,'summary':summary,'protocol':protocol,'closed_trades':simulator.trades,
        'replay_sha256':sha256(output/'replay-verification.json'),
        'limitations':['Retrospective cost diagnostic on an already inspected evaluation recording, not a new holdout.',
        'Long-only top training bucket; no cost gate or fitted threshold. Fixed 100 quote-unit exposure per completed trade.',
        'Local receipt-time entry delay is a scenario, not measured order latency. Book receipts can be stale.',
        'Exits use first quote at least five seconds after entry, with no extra exit-order latency; optimistic timing.',
        'Gap/boundary/depth failures leave unresolved positions; closed-trade totals are not complete portfolio P&L.',
        'Top-level displayed depth does not guarantee a fill. No queue simulation, exchange filters, rounding or market impact.',
        'Holding from delayed entry changes the forecast horizon; model forecasts originally target five seconds from decision.',
        'No real orders, model promotion or profitability certification.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',required=True,type=Path);p.add_argument('--model',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path);a=p.parse_args()
    try:
        print(json.dumps(run(a.capture,a.model,a.output_dir),indent=2));print(f'Completed: {a.output_dir}/report.json; diagnostic only.')
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f'Execution diagnostic stopped: {error}',file=sys.stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(main())
