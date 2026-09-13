"""Build the reproducible English results report from exported backtests."""
import csv
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def load(symbol,case,phase='holdout'):
    return json.loads((ROOT/'results'/f'{symbol}_{phase}_{case}'/'summary.json').read_text())

def main():
    lines=['# Our results — v0.2\n',
    '**Result: insufficient evidence to trade real money with these strategies.**\n',
    'These are historical simulations, not real trades or forecasts. Fixed universe: BTCUSDT and ETHUSDT. Period: January–March 2025, 25,920 five-minute candles per symbol (51,840 total), downloaded from the official Binance archive and verified against its checksums. The chosen quarter is a reproducible pilot study, not a representation of every regime or the current market.\n',
    'Protocol fixed before viewing results: select the highest January PnL among SMA 5/20, 12/48 with 26 bps separation, and 20/60 with 26 bps separation. Validate in February and evaluate in March without reselection. Both symbols selected SMA 20/60. Windows refer to five-minute bars (100 and 300 minutes); this is not second-scale scalping. The separation parameter is not a profit forecast.\n',
    'Each evaluation starts with 1,000 virtual USDT and a single position of up to 100 USDT, without leverage or proportional reinvestment. Maximum 12 entries per UTC day, a three-bar cooldown after exit, a halt after 5% peak drawdown, and a daily pause after a 2% loss. Signals precede the opening; fills occur at the next opening with impact. Risk exits occur on the next observation, not through an intrabar stop.\n',
    'Hypothetical base costs: 10 bps fees per side, 2 bps full spread, and 2 bps slippage per side. These are not confirmed account fees. A 0.000001 quantity step and 5 USDT minimum notional are laboratory parameters, not all historical Binance filters. Electricity and taxes are excluded.\n',
    '## February validation\n',
    '| Pair | Net PnL USDT | Closed trades | Maximum account drawdown |',
    '|---|---:|---:|---:|']
    for symbol in ('BTCUSDT','ETHUSDT'):
        r=load(symbol,'selected','validation')
        lines.append(f"| {symbol} | {r['net_pnl']:.6f} | {r['closed_trades']} | {r['max_drawdown_pct']:.3f}% |")
    lines+=['\n## Final evaluation: March, 744 hours\n',
    '| Pair | Strategy/cost | Net PnL USDT | Fees USDT | Trades | Maximum account drawdown |',
    '|---|---|---:|---:|---:|---:|']
    for symbol in ('BTCUSDT','ETHUSDT'):
        for case in ('baseline_5_20','selected','buy_hold_100','cash','selected_cost_zero','selected_fee_7_5','selected_stress'):
            r=load(symbol,case)
            lines.append(f"| {symbol} | {case} | {r['net_pnl']:.6f} | {r['fees']:.4f} | {r['closed_trades']} | {r['max_drawdown_pct']:.3f}% |")
    lines+=['\nThe 5/20 baseline permits up to 288 entries/day without cooldown, with the same loss limits. It adapts the v0.1 idea to candles rather than reproducing five-second intervals. `buy_hold_100` buys up to 100 USDT and holds the remainder in cash, without stops or rebalancing. `selected_cost_zero` removes fees and impact; `selected_fee_7_5` reduces fees only to 7.5 bps; `selected_stress` uses 15 bps fees, 5 bps slippage, and 10 bps spread. Parameters are not reoptimized.\n',
    '## Gains and losses per hour/second\n',
    '| Pair, selected strategy | Average USDT/h | Arithmetic average USDT/s | Worst hour USDT | Best hour USDT | Win rate | Profit factor |',
    '|---|---:|---:|---:|---:|---:|---:|']
    for symbol in ('BTCUSDT','ETHUSDT'):
        r=load(symbol,'selected')
        lines.append(f"| {symbol} | {r['average_pnl_per_hour']:.9f} | {r['average_pnl_per_second']:.12f} | {r['worst_hour_pnl']:.4f} | {r['best_hour_pnl']:.4f} | {r['win_rate_pct']:.2f}% | {r['profit_factor']:.4f} |")
    lines+=['\nHours are grouped in UTC and include equity changes from open positions. Closed-trade profits are recorded separately. All inventory is liquidated at the end with exit costs, reconciling total PnL with realized trades. The per-second average does NOT measure execution or intrasecond extremes. Averages include all 744 hours, including periods without exposure.\n',
    'ETH ended with only a few thousandths of a USDT in profit: economically indistinguishable from zero for this use, and additional costs make it negative. BTC moved from profit without costs to net loss. Stress loses on both symbols. Losing less than the baseline is not interpreted as a positive edge.\n',
    '## Two simultaneous accounts\n']
    curves=[]
    for symbol in ('BTCUSDT','ETHUSDT'):
        with (ROOT/'results'/f'{symbol}_holdout_selected'/'equity.csv').open() as f:
            curves.append(list(csv.DictReader(f)))
    peak=2000.;dd=0;out=[]
    for a,b in zip(*curves):
        assert a['timestamp']==b['timestamp']
        eq=float(a['equity'])+float(b['equity']);peak=max(peak,eq);dd=max(dd,(peak-eq)/peak*100)
        out.append({'timestamp':a['timestamp'],'equity_combined':eq})
    with (ROOT/'results'/'combined_equity.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=out[0].keys());w.writeheader();w.writerows(out)
    lines.append(f"Total virtual capital: 2,000 USDT. Combined PnL: {out[-1]['equity_combined']-2000:.6f} USDT. Maximum combined close-marked drawdown: {dd:.3f}%. This aggregates two independent accounts; it is NOT an implemented global risk limit.\n")
    runtime=json.loads((ROOT/'results'/'runtime.json').read_text())
    lines+=['## Measured requirements\n',f"The full benchmark took {runtime['wall_seconds']:.2f} seconds in the development environment, with peak Python allocations of {runtime['python_peak_allocated_mib']:.2f} MiB measured using tracemalloc. This is NOT total process RAM or a measurement of the user's i7; instrumentation adds overhead. It cannot establish trading latency. No GPU or external packages are used.\n",
    '## Limitations and reproducibility\n',
    'CSVs and hashes are included. `python3 benchmark.py` reproduces the tables; `python3 make_report.py` updates this report. No AI model was used and parameters were not adjusted to March results. Only historical periods were reserved, not genuinely unseen future data. Repeated tuning against March would turn it into training data.\n',
    'Missing elements include depth, maker queues, variable latency, partial fills, historical spread, exact historical filters, delistings, account-specific fees, other quarters, and demo validation. Drawdown observed at openings/closings may underestimate intrabar drawdown; there is no guaranteed stop. One quarter and two symbols cannot establish the probability of future profitability.\n',
    'Full results are in `results/comparison.csv`, `selection.json`, and directories containing `summary.json`, `trades.csv`, `hourly.csv`, and `equity.csv`. Other-bot research and references are in `research/ANALYSIS.md`.\n']
    (ROOT/'research'/'RESULTS.md').write_text('\n'.join(lines).rstrip()+'\n')
if __name__=='__main__':main()
