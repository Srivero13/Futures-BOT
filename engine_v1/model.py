"""Ridge forecast with train-only scaling and separate error calibration."""
from dataclasses import dataclass,asdict
import hashlib
import json
import math
import numpy as np

FEATURES=['return_1','momentum_5','momentum_20','volatility_20','relative_volume','range']


def feature_matrix(rows):
    """Vectorized causal features; the online 21-bar window matches batch output."""
    if not rows:return np.empty((0,len(FEATURES)))
    close=np.array([float(r['close']) for r in rows]);volume=np.array([float(r['volume']) for r in rows])
    high=np.array([float(r['high']) for r in rows]);low=np.array([float(r['low']) for r in rows])
    if not all(np.isfinite(a).all() for a in (close,volume,high,low)) or np.any(close<=0) or np.any(volume<0) or np.any(high<close) or np.any(low>close):
        raise ValueError('Invalid feature candles')
    returns=np.zeros(len(rows));returns[1:]=np.diff(np.log(close))
    x=np.full((len(rows),len(FEATURES)),np.nan)
    if len(rows)<=20:return x
    windows=np.lib.stride_tricks.sliding_window_view
    x[20:,0]=returns[20:]
    x[20:,1]=np.log(close[20:]/close[15:-5])
    x[20:,2]=np.log(close[20:]/close[:-20])
    x[20:,3]=windows(returns,20)[1:].std(axis=1)
    x[20:,4]=np.log((volume[20:]+1)/(windows(volume,20)[1:].mean(axis=1)+1))
    x[20:,5]=(high[20:]-low[20:])/close[20:]
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
    volatility_scaled:bool=False
    volatility_floor:float=1e-6

    def predict(self,x):
        x=np.asarray(x,dtype=float)
        if x.shape!=(len(FEATURES),):return None
        z=(x-self.mean)/self.scale
        if not np.isfinite(z).all() or np.max(np.abs(z))>8:return None
        result=float(np.dot(z,self.coef)+self.intercept)*self.target_scale(x)
        return result if math.isfinite(result) else None

    def target_scale(self,x):
        return max(float(x[3]),self.volatility_floor)*math.sqrt(self.horizon_bars)*10000 if self.volatility_scaled else 1.

    def decision(self,x,cost_bps,margin_bps=2):
        if not math.isfinite(float(cost_bps)) or float(cost_bps)<0 or not math.isfinite(margin_bps) or margin_bps<0:
            return {'enter':False,'reason':'invalid_cost'}
        predicted=self.predict(x)
        if predicted is None:return {'enter':False,'reason':'invalid_or_out_of_distribution'}
        lower=predicted-self.downside_buffer_bps*self.target_scale(x)
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
        if type(model.approved) is not bool or type(model.volatility_scaled) is not bool or not math.isfinite(model.volatility_floor) or model.volatility_floor<=0 or model.downside_buffer_bps<0 or not 0<=model.train_end_ms<=model.calibration_end_ms:raise ValueError('Invalid model metadata')
        if min(model.scale)<=0 or model.horizon_bars not in (1,3,5) or model.timeframe_ms!=60000:raise ValueError('Invalid model schema')
        return model


def fit_model(rows,x,symbol,horizon,fit_end,calibration_end,alpha=10,volatility_scaled=False):
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
    floor=max(1e-6,float(np.quantile(xf[:,3],.1)))
    fit_scale=np.maximum(xf[:,3],floor)*math.sqrt(horizon)*10000 if volatility_scaled else np.ones(len(xf))
    cal_scale=np.maximum(xc[:,3],floor)*math.sqrt(horizon)*10000 if volatility_scaled else np.ones(len(xc))
    target=yf/fit_scale
    mean=xf.mean(axis=0);scale=xf.std(axis=0);scale=np.where(scale<1e-12,1.,scale)
    z=(xf-mean)/scale;intercept=float(target.mean())
    # Solve augmented least squares via SVD; do not invert X'X.
    coef=np.linalg.lstsq(np.vstack([z,np.sqrt(alpha)*np.eye(z.shape[1])]),
                         np.concatenate([target-intercept,np.zeros(z.shape[1])]),rcond=None)[0]
    pred=((xc-mean)/scale@coef+intercept)*cal_scale
    residual=(pred-yc)/cal_scale
    rank=min(len(residual)-1,math.ceil((len(residual)+1)*.90)-1)
    buffer=max(0.,float(np.sort(residual)[rank]))
    return RidgeModel(symbol,horizon,mean.tolist(),scale.tolist(),coef.tolist(),intercept,buffer,
        rows[fit_end-1]['timestamp']+60000,rows[calibration_end-1]['timestamp']+60000,len(xf),len(xc),
        float(np.sqrt(np.mean((pred-yc)**2))),float(np.sqrt(np.mean(yc**2))),alpha,volatility_scaled=volatility_scaled,volatility_floor=floor)
