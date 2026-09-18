"""Acquire, audit and evaluate fixed rolling trade-flow development folds."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from train_v15 import timestamp
from walkforward_v16 import shift_month


def schedule(first_test, months, reserve_from):
    if not 1 <= months <= 6:
        raise ValueError('Use 1..6 test months')
    end = shift_month(first_test, months)
    if timestamp(end) > timestamp(reserve_from):
        raise ValueError('Test schedule crosses reserved boundary')
    return [dict(train_start=shift_month(first_test, i-2),
                 calibration_start=shift_month(first_test, i-1),
                 test_start=shift_month(first_test, i),
                 test_end=shift_month(first_test, i+1)) for i in range(months)]


def summarize(reports):
    if not reports:
        raise ValueError('No completed folds')
    result={'folds':len(reports),'flow_lower_rmse_than_candles_folds':0,
            'flow_lower_rmse_than_zero_folds':0,'candles_lower_rmse_than_zero_folds':0,
            'monthly':[]}
    for fold,report in reports:
        s=report['summary'];r=s['test_rmse_log_bps'];z=s['zero_rmse_log_bps']
        result['flow_lower_rmse_than_candles_folds']+=int(r['candles_plus_flow']<r['candles_only'])
        result['flow_lower_rmse_than_zero_folds']+=int(r['candles_plus_flow']<z)
        result['candles_lower_rmse_than_zero_folds']+=int(r['candles_only']<z)
        result['monthly'].append({'test_start':fold['test_start'],**s})
    return result


def run(a):
    folds=schedule(a.first_test,a.months,a.reserve_from)
    work=Path(a.output_dir).resolve()
    if work.exists():raise ValueError('Output directory exists; use a new directory. Downloads can be reused.')
    root=Path(a.root).resolve();candles=Path(a.candle_root).resolve()
    source=Path(__file__).resolve().parent
    months=[shift_month(a.first_test,i) for i in range(-2,a.months)]
    # Fail before downloading if the candle corpus is incomplete.
    for month in months:
        p=candles/f'binance-{a.symbol}-{month[:7]}.csv'
        if not p.is_file() or not p.with_suffix('.json').is_file():
            raise ValueError('Missing candle shard or manifest: '+str(p))
    work.mkdir(parents=True)
    atomic_json(work/'protocol.json',{'symbol':a.symbol,'folds':folds,'reserve_from':a.reserve_from,
        'horizon_minutes':15,'alpha':10,'training_window_months':1,
        'selection':'No parameter search or automatic model selection',
        'runner_sha256':sha256(Path(__file__))})
    def execute(script,*args):
        subprocess.run([sys.executable,'-u',str(source/script),*map(str,args)],check=True)
    audits={}
    for index,month in enumerate(months,1):
        print(f'[batch] month {index}/{len(months)}: {month[:7]}',flush=True)
        execute('download_tradeflow.py','--symbol',a.symbol,'--start',month,'--end',shift_month(month,1),
                '--reserve-from',a.reserve_from,'--root',root,'--max-total-gib',8,'--max-archive-mib',512)
        files=sorted(root.glob(f'{a.symbol}-aggTrades-{month[:7]}-*-flow.csv'))
        if not files:raise ValueError('Downloader produced no flow summaries')
        audit=work/f'{a.symbol}-{month[:7]}-alignment.json'
        execute('audit_tradeflow.py','--flow-files',*files,'--candle-files',
                candles/f'binance-{a.symbol}-{month[:7]}.csv','--symbol',a.symbol,
                '--reserve-from',a.reserve_from,'--output',audit)
        audits[month]=audit
    results=[]
    for index,fold in enumerate(folds,1):
        print(f'[batch] evaluation {index}/{len(folds)}: {fold["test_start"]}',flush=True)
        output=work/f'{a.symbol}-{fold["test_start"][:7]}-paired.json'
        execute('evaluate_tradeflow.py','--audits',*[audits[shift_month(fold['train_start'],i)] for i in range(3)],
                '--symbol',a.symbol,'--start',fold['train_start'],'--reserve-from',a.reserve_from,'--output',output)
        results.append((fold,json.loads(output.read_text())))
    report={'approved':False,'pnl':None,'summary':summarize(results),
        'fold_reports':[{**fold,'report':report} for fold,report in results],
        'limitations':['All months are retrospective development data, including previously inspected August.',
            'Rolling folds share training/calibration data; they are not independent experiments.',
            'One-month training windows and fixed parameters; no best-fold selection or profitability claim.',
            'No transaction-cost execution simulation or live model is created.']}
    atomic_json(work/'summary.json',report)
    print(json.dumps(report['summary'],indent=2))
    print(f'Completed: {work / "summary.json"}; research-only, unapproved.',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol',default='ETHUSDT')
    p.add_argument('--first-test',default='2026-05-01')
    p.add_argument('--months',type=int,default=4)
    p.add_argument('--reserve-from',default='2026-09-01')
    p.add_argument('--root',type=Path,default=Path('data/tradeflow-pilot'))
    p.add_argument('--candle-root',type=Path,default=Path('data/market-expanded'))
    p.add_argument('--output-dir',type=Path,required=True)
    try:run(p.parse_args())
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as error:
        print(f'Batch stopped: {error}',file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('Interrupted; completed downloads remain reusable.',file=sys.stderr);return 130
    return 0


if __name__=='__main__':raise SystemExit(main())
