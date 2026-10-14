"""UM02: fixed four-hour channel breakout development experiment."""
import argparse
from collections import deque
from decimal import Decimal,localcontext
import json
from pathlib import Path
from engine_v1.dataset import sha256
from research_usdm_bundle import load_bundle,weekly_summary
from usdm_sequence_accounting import account_sequence

PROTOCOL=dict(experiment='UM02',lookback_minutes=240,holding_minutes=240,
              entry_delay_seconds=60,absolute_quantity='0.05',fee_bps_per_side='5',
              impact_bps_per_side='2',settlement_grid_guard_minutes=2,
              rationale='Test continuation beyond a four-hour channel with a longer fixed hold; no claim of edge')


def near_grid(t):
    period=8*3600000
    remainder=t%period
    return min(remainder,period-remainder)<=120000


def plan(rows):
    highs=deque();lows=deque();trades=[];occupied_until=-1
    counts=dict(breakout_decisions_while_flat=0,grid_guard_skips=0,boundary_candidates_not_evaluated=0)
    for i,row in enumerate(rows):
        t=row['timestamp'];decision=t+60000
        if type(t) is not int or t%60000 or (i and t!=rows[i-1]['timestamp']+60000):
            raise ValueError('Continuous minute candles required')
        h,l,c=map(Decimal,(row['high'],row['low'],row['close']))
        if not all(v.is_finite() and v>0 for v in (h,l,c)) or not l<=c<=h:
            raise ValueError('Invalid candle bounds')
        while highs and highs[0][0]<i-240: highs.popleft()
        while lows and lows[0][0]<i-240: lows.popleft()
        direction=0
        if i>=240 and decision>=occupied_until:
            direction=1 if c>highs[0][1] else -1 if c<lows[0][1] else 0
        if direction:
            counts['breakout_decisions_while_flat']+=1
            entry=decision+60000;exit_time=entry+240*60000
            if near_grid(entry) or near_grid(exit_time):
                counts['grid_guard_skips']+=1
            elif i+242>=len(rows):
                counts['boundary_candidates_not_evaluated']+=1
                # This candidate would occupy the rest of the available recording.
                occupied_until=exit_time
            else:
                trades.append(dict(id=f'UM02-{decision}',decision_ms=decision,entry_ms=entry,exit_ms=exit_time,
                    quantity='0.05' if direction>0 else '-0.05',
                    channel_high=str(highs[0][1]),channel_low=str(lows[0][1]),signal_close=str(c),
                    entry_reference=rows[i+2]['open'],exit_reference=rows[i+242]['open']))
                occupied_until=exit_time
        # Signal excludes the current bar from the channel; append only afterwards.
        while highs and highs[-1][1]<=h: highs.pop()
        while lows and lows[-1][1]>=l: lows.pop()
        highs.append((i,h));lows.append((i,l))
    return trades,counts


def run(root):
    rows,marks,events,hashes=load_bundle(root)
    trades,counts=plan(rows)
    print(f'[UM02] accounting {len(trades)} trades',flush=True)
    ledger=account_sequence(trades,marks,events,'5','2')
    stress=account_sequence(trades,marks,events,'5','3')
    with localcontext() as ctx:
        ctx.prec=50
        profits=[Decimal(t['accounting']['scenario_net_pnl']) for t in ledger['trades']]
        excluding=str(Decimal(ledger['net_pnl'])-max(profits)) if profits else None
    summary={k:ledger[k] for k in ('closed_trades','net_pnl','reference_price_pnl','assumed_fees',
        'assumed_price_impact_cost','funding_cashflow','max_sampled_drawdown_quote','accounting_reconciled')}
    summary.update(counts,long_trades=sum(Decimal(t['quantity'])>0 for t in trades),
        short_trades=sum(Decimal(t['quantity'])<0 for t in trades),net_excluding_best_trade=excluding,
        extra_1bps_impact_per_side_net_pnl=stress['net_pnl'],exit_week_totals=weekly_summary(ledger))
    if any(sha256(p)!=h for p,h in hashes.items()): raise ValueError('Inputs changed during research')
    return dict(approved=False,experiment='UM02',status='development_only',protocol=PROTOCOL,
        summary=summary,trade_plan=trades,ledger=ledger,inputs_sha256=hashes,
        code_sha256={name:sha256(Path(__file__).parent/name) for name in
            ('research_usdm_breakout.py','research_usdm_bundle.py','usdm_sequence_accounting.py',
             'diagnose_usdm_roundtrip.py','diagnose_usdm_mark_path.py','funding_cashflows.py')},
        limitations=['Already-inspected development period; not independent validation.',
          'The eight-hour exclusion grid is a fixed research convention, not verified historical funding rules; unexpected boundary ambiguity fails.',
          'Candle-open reference fills and hypothetical costs; no capital, margin, liquidation or order execution.',
          'One fixed configuration; no search or automatic promotion. UM01 remains rejected.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink(): p.error('Output exists; choose a new path')
    r=run(a.bundle);a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f: f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r['summary'],indent=2))
    print(f'Completed: {a.output}; development-only, unapproved.')


if __name__=='__main__': main()
