"""Explain model entry gates without changing models, costs, or approvals."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
from backtest_v16 import Costs, D
from decimal import localcontext
from engine_v1.dataset import examples, segment, sha256
from engine_v1.fast import FastPredictor
from engine_v1.nonlinear import PolynomialModel, load_model
from engine_v1.operations import atomic_json
from engine_v1.training import Reservoir
from train_v15 import timestamp


class Distribution:
    def __init__(self):
        self.sample = Reservoir(capacity=100000, seed=161)
        self.count = 0
        self.total = 0.
        self.minimum = math.inf
        self.maximum = -math.inf

    def add(self, values):
        if not len(values):
            return
        if not np.isfinite(values).all():
            raise ValueError('Non-finite diagnostic values')
        self.sample.add(values)
        self.count += len(values)
        self.total += float(np.sum(values))
        self.minimum = min(self.minimum, float(np.min(values)))
        self.maximum = max(self.maximum, float(np.max(values)))

    def report(self):
        if not self.count:
            return {'count':0, 'mean':None, 'min':None, 'max':None, 'quantiles':None}
        return {'count':self.count, 'mean':self.total/self.count,
                'min':self.minimum, 'max':self.maximum,
                'quantiles':dict(zip(['p01','p05','p50','p95','p99'],
                                    map(float,np.quantile(self.sample.values,[.01,.05,.5,.95,.99])))),
                'quantile_sample_size':len(self.sample.values),
                'quantiles_approximate':self.count > len(self.sample.values)}


def diagnose(factory, model, start, end, costs=Costs(), progress=None):
    costs.validate()
    if start < model.calibration_end_ms or start >= end or start % 60000 or end % 60000:
        raise ValueError('Require minute-aligned dates at or after calibration')
    with localcontext() as context:
        context.prec = 50
        fee = D(costs.fee_bps)/10000
        impact = (D(costs.spread_bps)/2+D(costs.slippage_bps))/10000
        ratio = (1+impact)*(1+fee)/((1-impact)*(1-fee))
        threshold = math.log(float(ratio))*10000+costs.margin_bps
    predictor = model if isinstance(model,PolynomialModel) else FastPredictor(model)
    names = ('prediction_log_bps','buffer_log_bps','lower_bound_log_bps',
             'threshold_shortfall_log_bps','actual_return_log_bps')
    distributions = {name:Distribution() for name in names}
    total = accepted = raw_pass = lower_pass = buffer_blocked = covered = 0
    error = zero_error = 0.
    for batch in segment(factory,start,end):
        total += len(batch)
        predictions = predictor.batch(batch[:,2:8])
        valid = np.isfinite(predictions)
        x = batch[valid,2:8]
        p = predictions[valid]
        y = batch[valid,8]
        scale = (np.maximum(x[:,3],model.volatility_floor)*math.sqrt(model.horizon_bars)*10000
                 if model.volatility_scaled else np.ones(len(p)))
        buffer = model.downside_buffer_bps*scale
        lower = p-buffer
        for name,values in zip(names,(p,buffer,lower,threshold-lower,y)):
            distributions[name].add(values)
        accepted += len(p)
        raw_pass += int(np.sum(p > threshold))
        lower_pass += int(np.sum(lower > threshold))
        buffer_blocked += int(np.sum((p > threshold) & (lower <= threshold)))
        covered += int(np.sum(y >= lower))
        error += float(np.sum((p-y)**2))
        zero_error += float(np.sum(y*y))
        if progress:
            progress(total)
    if total == 0:
        raise ValueError('No examples in the requested interval')
    reason = ('all_examples_rejected' if not accepted else
              'raw_forecasts_never_clear_threshold' if not raw_pass else
              'calibration_buffer_blocks_all_raw_candidates' if not lower_pass else
              'some_calibrated_forecasts_clear_threshold')
    return {'approved':False,'pnl':None,'examples':total,'accepted':accepted,
        'ood_rejected':total-accepted,'entry_threshold_log_bps':threshold,
        'raw_forecast_above_threshold':raw_pass,
        'blocked_by_calibration_buffer':buffer_blocked,
        'calibrated_forecast_above_threshold':lower_pass,
        'diagnosis':reason,
        'rmse_log_bps':math.sqrt(error/accepted) if accepted else None,
        'zero_rmse_log_bps_same_rows':math.sqrt(zero_error/accepted) if accepted else None,
        'lower_bound_coverage':covered/accepted if accepted else None,
        'distributions':{k:v.report() for k,v in distributions.items()},
        'cost_assumptions':{'fee_bps_per_side':costs.fee_bps,'full_spread_bps':costs.spread_bps,
                            'slippage_bps_per_side':costs.slippage_bps,'margin_log_bps':costs.margin_bps},
        'notes':['Diagnostic only: raw-forecast counts are counterfactual, not recommended trades.',
                 'Positive shortfall means the lower bound is below the entry threshold; equality does not pass.',
                 'All distributions use accepted examples; labels overlap and are not independent.',
                 'Labels use next-open returns, with no execution delay or position simulation.',
                 'Label-end filtering excludes boundary examples; counts can differ from the execution backtest.',
                 'Gaps reset feature windows; this report does not certify continuous data coverage.',
                 'Means/extrema/counts use every accepted row; quantiles use a fixed-seed reservoir capped at 100000.',
                 'Previously inspected periods remain retrospective; no tuning or model promotion is performed.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files',nargs='+',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--start',required=True)
    parser.add_argument('--end',required=True)
    parser.add_argument('--output',type=Path,required=True)
    for name in ('fee_bps','spread_bps','slippage_bps','margin_bps'):
        parser.add_argument('--'+name.replace('_','-'),type=float,default=getattr(Costs(),name))
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError('Output exists; choose a new filename')
        costs = Costs(**{k:getattr(args,k) for k in ('fee_bps','spread_bps','slippage_bps','margin_bps')})
        costs.validate()
        paths = [p.resolve() for p in args.files]
        if len(set(paths)) != len(paths):
            raise ValueError('Duplicate input files')
        model_hash = sha256(args.model)
        model = load_model(args.model)
        sources = []
        print('[diagnostic] verifying inputs',file=sys.stderr,flush=True)
        for path in paths:
            digest = sha256(path)
            meta = json.loads(path.with_suffix('.json').read_text())
            if (meta.get('sha256'),meta.get('venue'),meta.get('symbol'),meta.get('timeframe_ms')) != (digest,'binance',model.symbol,60000):
                raise ValueError(f'Shard identity/checksum mismatch: {path}')
            sources.append({'file':str(path),'sha256':digest})
        started = time.monotonic()
        def progress(count):
            print(f'[diagnostic] examples={count:,} elapsed={time.monotonic()-started:.1f}s',file=sys.stderr,flush=True)
        report = diagnose(lambda:examples(paths,model.horizon_bars),model,
                          timestamp(args.start),timestamp(args.end),costs,progress)
        if sha256(args.model) != model_hash or any(sha256(p)!=s['sha256'] for p,s in zip(paths,sources)):
            raise ValueError('Input changed during diagnostics')
        report['spec'] = {'model_sha256':model_hash,'symbol':model.symbol,'venue':'binance',
                          'start':args.start,'end':args.end,'sources':sources,
                          'code_sha256':{str(p):sha256(p) for p in [Path(__file__),
                            *[Path(__file__).parent/'engine_v1'/f for f in
                              ('dataset.py','model.py','nonlinear.py','fast.py','training.py')],
                            Path(__file__).parent/'backtest_v16.py']}}
        atomic_json(args.output,report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('spec','notes')},indent=2))
        print(f'Completed: {args.output}; diagnostic only, unapproved.')
        return 0
    except (ValueError,OSError,KeyError,TypeError) as error:
        print(f'Diagnostic stopped: {error}',file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted; no complete report published.',file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
