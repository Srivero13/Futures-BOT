"""Report both fixed models on the same accepted holdout examples; never promote."""
import argparse
import json
from pathlib import Path
import numpy as np
from engine_v1.dataset import examples, segment
from engine_v1.fast import FastPredictor
from engine_v1.nonlinear import load_model, PolynomialModel
from engine_v1.operations import atomic_json
from train_v15 import timestamp


def compare(paths, linear, nonlinear, start, end):
    if linear.symbol != nonlinear.symbol or linear.horizon_bars != nonlinear.horizon_bars:
        raise ValueError('Models must share symbol and horizon')
    if not isinstance(nonlinear, PolynomialModel) or isinstance(linear, PolynomialModel):
        raise ValueError('Expected linear and polynomial models in that order')
    if start < max(linear.calibration_end_ms, nonlinear.calibration_end_ms) or start >= end:
        raise ValueError('Comparison must occur after calibration')
    counts = 0
    errors = np.zeros(3)
    predictor = FastPredictor(linear)
    for b in segment(lambda: examples(paths, linear.horizon_bars), start, end):
        p, q = predictor.batch(b[:,2:8]), nonlinear.batch(b[:,2:8])
        valid = np.isfinite(p) & np.isfinite(q)
        y = b[valid,8]
        counts += len(y)
        errors += [np.sum((p[valid]-y)**2),np.sum((q[valid]-y)**2),np.sum(y*y)]
    if counts == 0: raise ValueError('No jointly accepted examples')
    return {'common_accepted_examples':counts, 'linear_rmse':float(np.sqrt(errors[0]/counts)),
            'polynomial_rmse':float(np.sqrt(errors[1]/counts)), 'zero_rmse':float(np.sqrt(errors[2]/counts)),
            'approved':False,'note':'Retrospective comparison on identical accepted rows; not P&L, significance, or a promotion criterion.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files', nargs='+', type=Path, required=True)
    p.add_argument('--linear', type=Path, required=True)
    p.add_argument('--polynomial', type=Path, required=True)
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--output', type=Path, default=Path('data/comparison-v16.json'))
    a = p.parse_args()
    report = compare(a.files,load_model(a.linear),load_model(a.polynomial),timestamp(a.start),timestamp(a.end))
    atomic_json(a.output,report)
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
