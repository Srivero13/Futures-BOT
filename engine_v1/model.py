"""Ridge forecast with train-only scaling and separate error calibration."""
from dataclasses import dataclass,asdict
import hashlib
import json
import math
import numpy as np

FEATURES=['return_1','momentum_5','momentum_20','volatility_20','relative_volume','range']


def feature_matrix(rows):
    close=np.array([float(r['close']) for r in rows]);volume=np.array([float(r['volume']) for r in rows])
    returns=np.zeros(len(rows));returns[1:]=np.diff(np.log(close))
    x=np.full((len(rows),len(FEATURES)),np.nan)
    for i in range(20,len(rows)):
        x[i]=[returns[i],math.log(close[i]/close[i-5]),math.log(close[i]/close[i-20]),
              np.std(returns[i-19:i+1]),math.log((volume[i]+1)/(np.mean(volume[i-19:i+1])+1)),
              (float(rows[i]['high'])-float(rows[i]['low']))/close[i]]
    return x

@dataclass
class RidgeModel:
    symbol:str
    horizon_bars:int
    mean:list
    scale:list
    coef:list
    intercept:float
    downside_buffer_bps:float
    train_end_ms:int
    calibration_end_ms:int
    fit_rows:int
    calibration_rows:int
    calibration_rmse_bps:float
    zero_forecast_rmse_bps:float
    alpha:float=10.0
    features:tuple=tuple(FEATURES)
    timeframe_ms:int=60000
    approved:bool=False

    def predict(self,x):
        z=(np.asarray(x,dtype=float)-self.mean)/self.scale
        if not np.isfinite(z).all() or np.max(np.abs(z))>8:return None
        result=float(np.dot(z,self.coef)+self.intercept)
        return result if math.isfinite(result) else None

    def decision(self,x,cost_bps,margin_bps=2):
        predicted=self.predict(x)
        if predicted is None:return {'enter':False,'reason':'invalid_or_out_of_distribution'}
        lower=predicted-self.downside_buffer_bps
        # Labels are log returns: express the exact arithmetic cost in the same units.
        log_cost=math.log1p(float(cost_bps)/10000)*10000
        return {'enter':lower>log_cost+margin_bps,'predicted_bps':predicted,
                'lower_log_bps':lower,'cost_bps':float(cost_bps),'cost_log_bps':log_cost,'reason':'calibrated_cost_gate'}

    def save(self,path):
        payload=asdict(self);body=json.dumps(payload,sort_keys=True,allow_nan=False)
        path.write_text(json.dumps({'model':payload,'sha256':hashlib.sha256(body.encode()).hexdigest()},indent=2))

    @classmethod
    def load(cls,path):
        wrapper=json.loads(path.read_text());p=wrapper['model']
        if hashlib.sha256(json.dumps(p,sort_keys=True,allow_nan=False).encode()).hexdigest()!=wrapper['sha256']:
            raise ValueError('Model checksum mismatch')
        model=cls(**p)
        if model.features!=FEATURES and list(model.features)!=FEATURES:raise ValueError('Feature schema mismatch')
        if not len(model.mean)==len(model.scale)==len(model.coef)==len(FEATURES):raise ValueError('Invalid model dimension')
        if not all(math.isfinite(v) for v in model.mean+model.scale+model.coef+[model.intercept,model.downside_buffer_bps]):raise ValueError('Non-finite model')
        if min(model.scale)<=0 or model.horizon_bars not in (1,3,5) or model.timeframe_ms!=60000:raise ValueError('Invalid model schema')
        return model


def fit_model(rows,x,symbol,horizon,fit_end,calibration_end,alpha=10):
    # Feature at closed bar i; target from next open to open horizon bars later.
    # Purge labels crossing either segment boundary.
    if horizon not in (1,3,5) or alpha<=0:raise ValueError('Invalid model parameters')
    def examples(start,end,stride=1):
        ids=np.arange(max(20,start),end-horizon-1,stride)
        y=np.array([math.log(float(rows[i+1+horizon]['open'])/float(rows[i+1]['open']))*10000 for i in ids])
        return ids,x[ids],y
    fit_ids,xf,yf=examples(20,fit_end)
    cal_ids,xc,yc=examples(fit_end,calibration_end,horizon)
    if len(xf)<100 or len(xc)<30:raise ValueError('Insufficient fit/calibration samples')
    mean=xf.mean(axis=0);scale=xf.std(axis=0);scale=np.where(scale<1e-12,1.,scale)
    z=(xf-mean)/scale;intercept=float(yf.mean())
    # Solve augmented least squares via SVD; do not invert X'X.
    coef=np.linalg.lstsq(np.vstack([z,np.sqrt(alpha)*np.eye(z.shape[1])]),
                         np.concatenate([yf-intercept,np.zeros(z.shape[1])]),rcond=None)[0]
    pred=(xc-mean)/scale@coef+intercept
    residual=pred-yc
    rank=min(len(residual)-1,math.ceil((len(residual)+1)*.90)-1)
    buffer=max(0.,float(np.sort(residual)[rank]))
    return RidgeModel(symbol,horizon,mean.tolist(),scale.tolist(),coef.tolist(),intercept,buffer,
        rows[fit_end-1]['timestamp']+60000,rows[calibration_end-1]['timestamp']+60000,len(xf),len(xc),
        float(np.sqrt(np.mean((pred-yc)**2))),float(np.sqrt(np.mean(yc**2))),alpha)
