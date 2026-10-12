"""UM01: fixed one-week causal momentum development experiment, no approval."""
import argparse
from datetime import date,timedelta
from decimal import Decimal,localcontext
import json
from pathlib import Path
from batch_usdm_marks import audit_marks
from diagnose_usdm_exposure import run as verify_week
from engine_v1.dataset import candles,sha256
from usdm_sequence_accounting import account_sequence


def signals(rows):
    """Odd UTC hours at :01, using closes through :00; 60-minute lookback."""
    result=[]
    for i,row in enumerate(rows):
        t=row['timestamp']
        if type(t) is not int or t%60000 or (i and t!=rows[i-1]['timestamp']+60000):
            raise ValueError('Expected continuous minute candles')
        c=Decimal(row['close'])
        if not c.is_finite() or c<=0:
            raise ValueError('Invalid close')
        if i<60 or t%3600000 or (t//3600000)%2!=1:
            continue
        with localcontext() as ctx:
            ctx.prec=50
            score=(c/Decimal(rows[i-60]['close'])).ln()*10000
        if abs(score)<Decimal('20'):
            continue
        result.append(dict(decision_ms=t+60000,entry_ms=t+120000,exit_ms=t+3720000,
                           score_log_bps=str(score),quantity='0.05' if score>0 else '-0.05'))
    return result


def plan(rows):
    selected=signals(rows)
    by_time={r['timestamp']:r for r in rows}
    trades=[];unclosed=0
    for s in selected:
        if s['entry_ms'] not in by_time or s['exit_ms'] not in by_time:
            unclosed+=1
            continue
        trades.append(dict(s,id=f"UM01-{s['decision_ms']}",
                           entry_reference=by_time[s['entry_ms']]['open'],
                           exit_reference=by_time[s['exit_ms']]['open']))
    return trades,unclosed


def run(first,batch,spot,funding,marks_first,marks_batch):
    verified=verify_week(first,batch,spot,funding)
    hashes=dict(verified['inputs_sha256']);rows=[];marks=[]
    for i in range(7):
        day=date(2026,8,1)+timedelta(days=i)
        folder=Path(first) if i==0 else Path(batch)/str(day)
        rows.extend(candles([folder/f'binance-usdm-ETHUSDT-{day}.csv']))
        mfolder=Path(marks_first) if i==0 else Path(marks_batch)/str(day)
        print(f'[UM01] auditing marks {day}',flush=True)
        audited=audit_marks(mfolder,day)
        hashes.update(audited['inputs_sha256'])
        marks.extend(json.loads((mfolder/'marks.json').read_text()))
    trades,unclosed=plan(rows)
    events=json.loads((Path(funding)/'funding.json').read_text())
    print(f'[UM01] accounting {len(trades)} trades',flush=True)
    ledger=account_sequence(trades,marks,events,'5','2')
    profits=[Decimal(t['accounting']['scenario_net_pnl']) for t in ledger['trades']]
    with localcontext() as ctx:
        ctx.prec=50
        excluding=str(Decimal(ledger['net_pnl'])-max(profits)) if profits else None
    if any(sha256(p)!=h for p,h in hashes.items()):
        raise ValueError('Inputs changed during experiment')
    summary={k:ledger[k] for k in ('closed_trades','net_pnl','reference_price_pnl','assumed_fees',
        'assumed_price_impact_cost','funding_cashflow','max_sampled_drawdown_quote','accounting_reconciled')}
    summary.update(long_trades=sum(Decimal(t['quantity'])>0 for t in trades),
                   short_trades=sum(Decimal(t['quantity'])<0 for t in trades),
                   boundary_candidates_not_evaluated=unclosed,
                   net_pnl_excluding_best_trade=excluding)
    return dict(approved=False,experiment='UM01',status='development_only',summary=summary,
                protocol=dict(lookback_minutes=60,threshold_log_bps=20,holding_minutes=60,
                    decision_schedule='Odd UTC hours at :01',entry_delay_seconds=60,
                    absolute_quantity='0.05',fee_bps_per_side='5',impact_bps_per_side='2'),
                trade_plan=trades,ledger=ledger,inputs_sha256=hashes,
                runner_sha256=sha256(Path(__file__)),
                limitations=['This week was already inspected; it is development data, not untouched validation.',
                    'Past momentum threshold is not a forecast of returns or a profitability gate.',
                    'Fixed hypothetical fees and candle-open price impact, not actual fills or account fees.',
                    'No capital sizing, margin, liquidation or live trading; funding schedule completeness unverified.',
                    'End-boundary candidates are disclosed and excluded; no incomplete trade is treated as zero P&L.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('first-pilot','batch-root','spot-root','funding-dir','marks-first','marks-batch','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        p.error('Output exists; choose a new path')
    r=run(a.first_pilot,a.batch_root,a.spot_root,a.funding_dir,a.marks_first,a.marks_batch)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r['summary'],indent=2))
    print(f'Completed: {a.output}; development only, unapproved.')


if __name__=='__main__':
    main()
