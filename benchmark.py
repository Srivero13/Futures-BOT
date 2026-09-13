"""Fixed protocol: select in Jan, validate Feb, untouched holdout March 2025."""
import csv
from dataclasses import replace
import json
from pathlib import Path
import time
import tracemalloc
from backtest import Params, read_candles, simulate, save_result
ROOT=Path(__file__).resolve().parent

def main():
    start=time.perf_counter(); tracemalloc.start()
    root=ROOT/'results'; root.mkdir(exist_ok=True)
    summaries=[]; selections={}
    candidates=[Params(fast=5,slow=20),Params(fast=12,slow=48,gap_bps=26),Params(fast=20,slow=60,gap_bps=26)]
    for symbol in ('BTCUSDT','ETHUSDT'):
        rows=read_candles(ROOT/'datasets'/f'{symbol}-5m-2025Q1.csv')
        jan=[r for r in rows if r['timestamp']<1738368000]
        feb=[r for r in rows if 1738368000<=r['timestamp']<1740787200]
        mar=[r for r in rows if r['timestamp']>=1740787200]
        ranked=[simulate(jan,p)['summary'] for p in candidates]
        chosen=max(range(len(ranked)),key=lambda i:ranked[i]['net_pnl'])
        p=candidates[chosen]
        selections[symbol]={'training_candidates':ranked,'chosen_index':chosen,
                            'rule':'Highest January net PnL, fixed candidate order breaks ties. No reselection after validation.'}
        for phase,data,warmup in [('validation',feb,[r['close'] for r in jan]),('holdout',mar,[r['close'] for r in jan+feb])]:
            cases=[('selected',p,'sma'),('baseline_5_20',Params(cooldown_bars=0,max_entries_day=288),'sma'),
                   ('cash',p,'cash'),('buy_hold_100',p,'hold')]
            if phase=='holdout':
                cases += [('selected_cost_zero',replace(p,fee_bps=0,spread_bps=0,slippage_bps=0),'sma'),
                          ('selected_fee_7_5',replace(p,fee_bps=7.5),'sma'),
                          ('selected_stress',replace(p,fee_bps=15,slippage_bps=5,spread_bps=10),'sma')]
            for name,params,strategy in cases:
                result=simulate(data,params,strategy,warmup)
                result['summary'].update(symbol=symbol,phase=phase,case=name)
                save_result(result,root/f'{symbol}_{phase}_{name}')
                summaries.append(result['summary'])
    (root/'selection.json').write_text(json.dumps(selections,indent=2)+'\n')
    fields=['symbol','phase','case','net_pnl','return_pct','fees','closed_trades','win_rate_pct',
            'profit_factor','max_drawdown_pct','average_pnl_per_hour','average_pnl_per_second',
            'worst_hour_pnl','best_hour_pnl','halted']
    with (root/'comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(summaries)
    elapsed=time.perf_counter()-start
    _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    (root/'runtime.json').write_text(json.dumps({'wall_seconds':elapsed,'python_peak_allocated_mib':peak/2**20,
        'note':'Development host, not user i7. tracemalloc enabled; not a trading latency benchmark.'},indent=2)+'\n')
    for r in summaries:
        if r['phase']=='holdout': print({k:r[k] for k in ['symbol','case','net_pnl','fees','closed_trades','max_drawdown_pct']})
if __name__=='__main__': main()
