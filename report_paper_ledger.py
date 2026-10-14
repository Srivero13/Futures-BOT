"""Read-only reconciliation of the current multi-account paper ledger."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from engine_v1.core import dec, monetary


@monetary
def report(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('BEGIN')  # All reads share one committed snapshot, including WAL.
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('SQLite integrity check failed')
        states={key:json.loads(raw) for key,raw in db.execute('SELECT id,state FROM accounts ORDER BY id')}
        if not states: raise ValueError('No paper accounts found')
        replay={key:dict(cash=dec(a['capital']),qty=dec(0),basis=dec(0),
                         realized=dec(0),fees=dec(0),buys=0,sells=0)
                for key,a in states.items()}
        issues=[]
        events=0
        for event_id,ts,key,raw in db.execute('SELECT id,timestamp_ms,account,payload FROM events ORDER BY id'):
            events+=1
            if key not in states: raise ValueError('Trade references an unknown account')
            trade=json.loads(raw); state=states[key]; account=replay[key]
            if trade['account']!=key or trade['symbol']!=state['symbol'] or trade['timestamp_ms']!=ts:
                raise ValueError('Trade identity differs from event record')
            qty,price,fee=map(dec,(trade['quantity'],trade['price'],trade['fee']))
            if qty<=0 or price<=0 or fee<0: raise ValueError('Invalid trade amount, price or fee')
            if trade['action']=='BUY':
                if account['qty']!=0: raise ValueError('Overlapping paper buys')
                account['basis']=qty*price+fee
                account['cash']-=account['basis']
                account['qty']=qty; account['buys']+=1
            elif trade['action']=='SELL':
                if qty!=account['qty']: raise ValueError('Sale quantity differs from open paper position')
                proceeds=qty*price-fee
                account['realized']+=proceeds-account['basis']
                account['cash']+=proceeds
                account['qty']=dec(0);account['basis']=dec(0);account['sells']+=1
            else: raise ValueError('Unexpected paper trade action')
            account['fees']+=fee
            for field in ('cash','qty','realized'):
                if abs(account[field]-dec(trade[field]))>dec('1e-40'):
                    issues.append({'account':key,'event_id':event_id,'field':field,'scope':'trade_payload'})
        output=[]
        for key,state in states.items():
            account=replay[key]
            for field in ('cash','qty','basis','realized','fees'):
                if abs(account[field]-dec(state[field]))>dec('1e-40'):
                    issues.append({'account':key,'field':field,'scope':'stored_account'})
            # This mark is historical and may precede the newest market prices.
            output.append({'account':key,'symbol':state['symbol'],
                'initial_capital':str(dec(state['capital'])),
                'reconstructed':{k:str(v) if k not in ('buys','sells') else v for k,v in account.items()},
                'last_recorded_equity':state['last_equity'],
                'last_recorded_mark_ms':state['last_timestamp_ms'],
                'historical_marked_pnl':str(dec(state['last_equity'])-dec(state['capital'])),
                'open_position':account['qty']!=0,
                'halted':state['halted'],'day_halted':state['day_halted']})
        return {'approved':False,'scope':'local paper ledger only','reconciled':not issues,
                'trade_events':events,'accounts':output,'discrepancies':issues,
                'note':'Realized P&L is reconstructed from recorded paper fills. Equity marks are historical; no current valuation, execution-quality or profitability certification.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database',type=Path)
    args=parser.parse_args()
    try:
        result=report(args.database)
        print(json.dumps(result,indent=2))
        return 0 if result['reconciled'] else 2
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        parser.exit(2,f'Paper report failed: {error}\n')


if __name__=='__main__':raise SystemExit(main())
