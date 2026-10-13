"""Verify the optional CUDA research backend using a fixed synthetic signal."""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np


def check():
    import torch
    from engine_v1.research_mlp import fit_predict

    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; this check requires a working GPU and never falls back to CPU')
    rng = np.random.default_rng(4)
    x = rng.normal(size=(2000, 3))
    y = 3 * x[:, 0] - 2 * x[:, 1]
    torch.cuda.synchronize()
    started = time.monotonic()
    prediction = fit_predict(x[:1500], y[:1500], [x[1500:]], device='cuda', epochs=40)[0]
    torch.cuda.synchronize()
    elapsed = time.monotonic() - started
    prediction = np.asarray(prediction)
    if prediction.shape != y[1500:].shape or not np.isfinite(prediction).all():
        raise ValueError('Invalid CUDA prediction shape or non-finite output')
    mse = float(np.mean((prediction - y[1500:]) ** 2))
    zero_mse = float(np.mean(y[1500:] ** 2))
    if not np.isfinite(mse) or mse >= zero_mse * .15:
        raise ValueError(f'CUDA learning control failed: MSE={mse}, zero MSE={zero_mse}')
    return {
        'approved': False, 'cuda_training_check_passed': True,
        'device': 'cuda', 'gpu_name': torch.cuda.get_device_name(0),
        'torch_version': str(torch.__version__), 'torch_cuda_version': torch.version.cuda,
        'training_rows': 1500, 'evaluation_rows': 500, 'epochs': 40,
        'mse': mse, 'zero_mse': zero_mse, 'mse_ratio': mse / zero_mse,
        'elapsed_seconds': elapsed,
        'scope': 'Synthetic learning control only; no market data, model export, orders or strategy approval. Not a hardware endurance test or speed benchmark.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new report path; existing reports are not overwritten')
    print('[cuda-check] starting fixed synthetic learning control', flush=True)
    report = check()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except (ImportError, RuntimeError, ValueError, OSError) as error:
        print(f'CUDA check failed: {error}', file=sys.stderr)
        raise SystemExit(2)
