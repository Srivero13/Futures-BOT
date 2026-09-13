"""Read-only metrics from paper ledger; not a live brokerage account."""
import argparse
import json
import sqlite3
from pathlib import Path

def report(path):
    uri=Path(path).resolve().as_uri()+'?mode=ro'
    db=sqlite3.connect(uri,uri=True)
    rows=db.execute('SELECT timestamp,kind,price,qty,fee,equity FROM events ORDER BY id').fetchall()
    meta=db.execute('SELECT config FROM metadata WHERE id=1').fetchone()
    config=json.loads(meta[0]) if meta else {}
    db.close()
    if not rows: return {'status':'no data'}
    # Initial capital reconstructs first event before fill using event cost and equity mark.
    # Require explicit initial capital from CLI, since old ledger does not persist original config.
    return rows,config

def main():
    p=argparse.ArgumentParser();p.add_argument('database');p.add_argument('--initial-capital',type=float,required=True)
    a=p.parse_args();data=report(a.database)
    if isinstance(data,dict): print(json.dumps(data));return
    rows,config=data
    if config.get('initial_cash') != a.initial_capital:
        raise ValueError('Initial capital does not match the ledger')
    if isinstance(rows,dict): print(json.dumps(rows));return
    total=rows[-1][5]-a.initial_capital
    elapsed=rows[-1][0]-rows[0][0]
    rate_allowed=elapsed>=3600 and config.get('source')=='binance_public'
    fees=sum(r[4] for r in rows)
    peak=a.initial_capital;dd=0;basis=0;realized=0;closed=0
    for ts,kind,price,qty,fee,equity in rows:
        peak=max(peak,equity);dd=max(dd,(peak-equity)/peak*100)
        if kind=='BUY':basis=price*qty+fee
        elif kind in ('SELL','STOP'):
            realized+=price*qty-fee-basis;basis=0;closed+=1
    print(json.dumps({'scope':'local paper only','net_pnl':total,'realized_pnl':realized,
        'unrealized_pnl':round(total-realized,10),'fees':fees,'closed_trades':closed,
        'max_drawdown_pct':dd,'observed_seconds':elapsed,
        'arithmetic_pnl_per_hour':total/elapsed*3600 if rate_allowed else None,
        'arithmetic_pnl_per_second':total/elapsed if rate_allowed else None,
        'warning':'Rates suppressed for synthetic data or <1 hour. Otherwise arithmetic only, not forecasts.'},indent=2))
if __name__=='__main__':main()
