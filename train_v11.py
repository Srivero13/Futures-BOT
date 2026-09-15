"""Predeclared rolling evaluation; no automatic promotion to current trading."""
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import time
import numpy as np
from engine_v1.core import dec
from engine_v1.model import feature_matrix,fit_model
from engine_v1.operations import atomic_json
from train_v1 import load_rows,evaluate
ROOT=Path(__file__).resolve().parent


def block_interval(values,seed=110,resamples=2000,block=3):
    """Circular moving-block bootstrap of mean daily PnL, not a profit guarantee."""
    v=np.asarray(values,dtype=float)
    if len(v)<7 or not np.isfinite(v).all():return None
    rng=np.random.default_rng(seed);starts=rng.integers(0,len(v),size=(resamples,int(np.ceil(len(v)/block))))
    indices=(starts[:,:,None]+np.arange(block))%len(v)
    means=v[indices.reshape(resamples,-1)[:,:len(v)]].mean(axis=1)
    return {'lower':float(np.quantile(means,.025)),'upper':float(np.quantile(means,.975)),
        'mean_daily':float(v.mean()),'days':len(v),'block_days':block,'resamples':resamples,'seed':seed}


def promote(model,summary):
    interval=block_interval(summary['daily_pnl'])
    approved=(summary['closed_trades']>=30 and dec(summary['net_pnl'])>0 and
        model.calibration_rmse_bps<model.zero_forecast_rmse_bps and interval is not None and interval['lower']>0)
    return approved,interval


def prediction_metrics(model,rows,features,start,end):
    errors=[];zeros=[];coverage=[]
    for i in range(start,end-model.horizon_bars-1,model.horizon_bars):
        predicted=model.predict(features[i])
        if predicted is None:continue
        y=np.log(float(rows[i+1+model.horizon_bars]['open'])/float(rows[i+1]['open']))*10000
        errors.append((predicted-y)**2);zeros.append(y*y)
        coverage.append(y>=predicted-model.downside_buffer_bps*model.target_scale(features[i]))
    return {'count':len(errors),'rmse_log_bps':float(np.sqrt(np.mean(errors))) if errors else None,
        'zero_rmse_log_bps':float(np.sqrt(np.mean(zeros))) if zeros else None,
        'lower_bound_coverage':float(np.mean(coverage)) if coverage else None}


def ts(date):return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()*1000)


def main():
    root=ROOT/'reports/v1.1';protocol=json.loads((root/'PROTOCOL.json').read_text());started=time.perf_counter()
    report={'version':'1.1.0','protocol':protocol,'protocol_sha256':hashlib.sha256((root/'PROTOCOL.json').read_bytes()).hexdigest(),
        'environment':{'python':platform.python_version(),'numpy':np.__version__,'machine':platform.machine()},'datasets':{},'folds':[]}
    for symbol in protocol['symbols']:
        path=ROOT/'datasets'/f'{symbol}-1m-2025Q2Q3.csv';rows=load_rows(path)
        t0=time.perf_counter();x=feature_matrix(rows)
        report['datasets'][symbol]={'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'feature_seconds':time.perf_counter()-t0}
        times=np.array([r['timestamp'] for r in rows])
        for month in protocol['test_months']:
            year,mon=map(int,month.split('-'));begin=ts(month+'-01');end_ts=ts(f'{year if mon<12 else year+1}-{mon+1 if mon<12 else 1:02d}-01')
            bounds=[int(np.searchsorted(times,t)) for t in (begin-56*86400000,begin-28*86400000,begin-14*86400000,begin,end_ts)]
            start,fit_end,cal_end,test_start,test_end=bounds
            local=rows[start:test_end];features=x[start:test_end];fit_end-=start;cal_end-=start;test_start-=start;test_end-=start
            candidates=[]
            for scaled in (False,True):
                for horizon in protocol['horizons_minutes']:
                    model=fit_model(local,features,symbol,horizon,fit_end,cal_end,alpha=protocol['alpha'],volatility_scaled=scaled)
                    summary,_=evaluate(local,features,model,cal_end,test_start,include_daily=True)
                    approved,interval=promote(model,summary)
                    candidates.append({'model':model,'validation':summary,'approved':approved,'daily_mean_95_interval':interval})
            # Cash participates explicitly; inactive or losing models never win deployment by a tie.
            eligible=[c for c in candidates if c['approved']]
            ranked=max(candidates,key=lambda c:dec(c['validation']['net_pnl']))
            selected=max(eligible,key=lambda c:dec(c['validation']['net_pnl'])) if eligible else None
            model=(selected or ranked)['model'];model.approved=selected is not None
            fold={'symbol':symbol,'test_month':month,'deployment':'model' if selected else 'cash',
                'boundaries_ms':{'fit_start':local[0]['timestamp'],'fit_end':local[fit_end]['timestamp'],'calibration_end':local[cal_end]['timestamp'],'validation_end':begin,'test_end':end_ts},
                'candidates':[{**{k:v for k,v in c.items() if k!='model'},'model':asdict(c['model'])} for c in candidates],
                'ranked_candidate':{'horizon':model.horizon_bars,'volatility_scaled':model.volatility_scaled},'tests':[]}
            # Evaluate the validation-ranked candidate even if rejected, clearly labeled research-only.
            scenarios=[('candidate_base',{}),('candidate_fast',{'latency_ms':50}),('candidate_slow',{'latency_ms':1000}),
                ('candidate_stress',{'fees':'15','slip':'5','spread':'10','latency_ms':1000}),
                ('momentum_reference',{'strategy':'sma'}),('cash',{'strategy':'cash'})]
            for name,kwargs in scenarios:
                summary,trades=evaluate(local,features,model,test_start,test_end,include_daily=True,**kwargs)
                summary['case']=name;summary['daily_mean_95_interval']=block_interval(summary['daily_pnl']);fold['tests'].append(summary)
                atomic_json(root/f'{symbol}-{month}-{name}-trades.json',trades)
            # All diagnostic test scores are reported only after validation selection.
            # They must never feed back into selection or promotion.
            for candidate,serialized in zip(candidates,fold['candidates']):
                serialized['test_prediction']=prediction_metrics(candidate['model'],local,features,test_start,test_end)
            fold['test_prediction']=prediction_metrics(model,local,features,test_start,test_end)
            report['folds'].append(fold)
            model_dir=root/'models';model_dir.mkdir(exist_ok=True);model.save(model_dir/f'{symbol}-{month}.json')
            atomic_json(root/'evaluation.json',report)
            print(symbol,month,'deployment:',fold['deployment'],'research PnL:',fold['tests'][0]['net_pnl'],flush=True)
    report['runtime_seconds']=time.perf_counter()-started
    atomic_json(root/'evaluation.json',report)
if __name__=='__main__':main()
