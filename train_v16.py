"""Guarded, restartable CPU research training. No live orders or model promotion."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time

# Bound default BLAS parallelism before importing numerical libraries.
for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ.setdefault(name, '1')


def run_training(paths, venue, symbol, output, train_end, calibration_end, test_end,
                 model_kind='polynomial', horizon=3, alpha=10., chunk_size=4096, verbose=True):
    import math
    import re
    import numpy as np
    from engine_v1.dataset import examples, sha256
    from engine_v1.nonlinear import load_model
    from engine_v1.operations import atomic_json, process_lock
    from engine_v1.training import fit_stream, evaluate_stream
    if not all(re.fullmatch(r'[A-Za-z0-9_-]{1,32}', v) for v in (venue, symbol)):
        raise ValueError('Use letters, digits, underscores or hyphens for venue/symbol')
    if model_kind not in ('linear', 'polynomial') or horizon not in (1, 3, 5, 15, 60):
        raise ValueError('Unsupported model or horizon')
    if not 32 <= chunk_size <= 65536 or not math.isfinite(alpha) or alpha <= 0:
        raise ValueError('Use chunk size 32..65536 and positive finite alpha')
    if not 0 < train_end < calibration_end < test_end or any(t % 60000 for t in (train_end, calibration_end, test_end)):
        raise ValueError('Require ordered, minute-aligned fit/calibration/test boundaries')
    paths = [Path(p).resolve() for p in paths]
    if not paths or len(set(paths)) != len(paths):
        raise ValueError('Supply unique chronological CSV/CSV.gz files')
    sources = []
    for path in paths:
        if not path.is_file():
            raise ValueError(f'Dataset not found: {path}. Download data first; check wildcard matches.')
        digest = sha256(path)
        sidecar = path.with_suffix('.json')
        meta = json.loads(sidecar.read_text()) if sidecar.exists() else None
        if meta and (meta.get('sha256') != digest or meta.get('venue') != venue or meta.get('symbol') != symbol or meta.get('timeframe_ms') != 60000):
            raise ValueError(f'Shard identity/checksum mismatch: {path.name}')
        sources.append({'file': path.name, 'sha256': digest, 'bytes': path.stat().st_size,
                        'provenance': meta or 'Local import; venue supplied by operator'})
    algorithm_files = ['dataset.py', 'training.py', 'nonlinear.py', 'model.py']
    algorithm = hashlib.sha256((''.join(sha256(Path(__file__).parent/'engine_v1'/f) for f in algorithm_files)+sha256(Path(__file__))).encode()).hexdigest()
    spec = {'version': '1.6', 'algorithm_sha256': algorithm, 'numpy': np.__version__, 'python': platform.python_version(),
            'venue': venue, 'symbol': symbol, 'model_kind': model_kind, 'horizon': horizon, 'alpha': alpha,
            'chunk_size': chunk_size, 'train_end_ms': train_end, 'calibration_end_ms': calibration_end,
            'test_end_ms': test_end, 'sources': sources}
    identity = hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()
    directory = Path(output) / f'{venue}-{symbol}-{model_kind}-{identity[:16]}'
    directory.mkdir(parents=True, exist_ok=True)
    status_path = directory/'status.json'
    model_path = directory/'model.json'
    report_path = directory/'evaluation.json'
    checkpoint = directory/'fit-complete.json'
    completion = directory/'complete.json'
    started = time.monotonic()
    last = [0., None]

    def progress(stage, rows=0, force=False):
        now = time.monotonic()
        if not force and last[1] == stage and now-last[0] < 1:
            return
        if shutil.disk_usage(directory).free < 1024**3:
            raise OSError('Less than 1 GiB free on output disk; free space and rerun')
        status = {'run_id': identity, 'state': 'running', 'stage': stage, 'rows': rows,
                  'timestamp_ms': int(time.time()*1000), 'elapsed_seconds': now-started}
        atomic_json(status_path, status)
        if verbose: print(f'{stage}: {rows:,} rows | {now-started:.1f}s', flush=True)
        last[:] = [now, stage]

    def verify_inputs():
        for path, source in zip(paths, sources):
            if sha256(path) != source['sha256']:
                raise ValueError('Input changed during training; restore it or begin a new run')

    # The lock is acquired before any mutable run state, including status.
    with process_lock(directory/'run.lock'):
        try:
            if completion.exists():
                done = json.loads(completion.read_text())
                if done['run_id'] != identity or done['model_sha256'] != sha256(model_path) or done['report_sha256'] != sha256(report_path):
                    raise ValueError('Completed run artifact integrity check failed')
                load_model(model_path)
                atomic_json(status_path, {'run_id': identity, 'state': 'complete', 'timestamp_ms': int(time.time()*1000)})
                return directory, json.loads(report_path.read_text())
            progress('preflight', force=True)
            atomic_json(directory/'spec.json', spec)
            factory = lambda: examples(paths, horizon=horizon, chunk_size=chunk_size)
            if checkpoint.exists():
                saved = json.loads(checkpoint.read_text())
                if saved['run_id'] != identity or saved['model_sha256'] != sha256(model_path):
                    raise ValueError('Fit checkpoint integrity check failed')
                model = load_model(model_path)
                calibration = saved['calibration']
                progress('resume_evaluation', force=True)
            else:
                # Check every requested segment before expensive fitting begins.
                counts = [0, 0, 0]
                for batch in factory():
                    t, label_end = batch[:, 0], batch[:, 1]
                    counts[0] += int(np.sum(label_end < train_end))
                    counts[1] += int(np.sum((t >= train_end) & (label_end < calibration_end) & ((t//60000).astype(np.int64) % horizon == 0)))
                    counts[2] += int(np.sum((t >= calibration_end) & (label_end < test_end)))
                    progress('validate_data', sum(counts))
                if counts[0] < 100 or counts[1] < 30 or counts[2] < 30:
                    raise ValueError(f'Insufficient fit/calibration/test examples: {counts}; require at least 100/30/30. Check UTC dates and gaps.')
                model, calibration = fit_stream(factory, symbol, horizon, train_end, calibration_end,
                                                alpha, model_kind=model_kind, progress=progress)
                verify_inputs()
                model.save(model_path)
                load_model(model_path)
                atomic_json(checkpoint, {'run_id': identity, 'model_sha256': sha256(model_path), 'calibration': calibration})
            metrics = evaluate_stream(factory, model, calibration_end, test_end, progress=progress)
            verify_inputs()
            if model.approved:
                raise ValueError('Research model unexpectedly approved')
            report = {'version': '1.6', 'run_id': identity, 'spec': spec, 'fit_rows': model.fit_rows,
                      'calibration_rows': model.calibration_rows, 'feature_count': len(model.features),
                      'calibration': calibration, 'holdout': metrics, 'approved': False,
                      'elapsed_this_attempt_seconds': time.monotonic()-started,
                      'note': 'Historical forecast diagnostics, not P&L. Resumption is from a completed fit, not a partial QR pass.'}
            atomic_json(report_path, report)
            atomic_json(completion, {'run_id': identity, 'model_sha256': sha256(model_path), 'report_sha256': sha256(report_path)})
            atomic_json(status_path, {'run_id': identity, 'state': 'complete', 'timestamp_ms': int(time.time()*1000)})
            return directory, report
        except BaseException as error:
            # Best effort only: disk failures must not mask the original exception.
            try:
                atomic_json(status_path, {'run_id': identity, 'state': 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                                         'error_type': type(error).__name__, 'message': str(error), 'timestamp_ms': int(time.time()*1000)})
            except OSError:
                pass
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', nargs='+', type=Path, required=True)
    parser.add_argument('--venue', required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--train-end', required=True)
    parser.add_argument('--calibration-end', required=True)
    parser.add_argument('--test-end', required=True)
    parser.add_argument('--model', choices=['linear', 'polynomial'], default='polynomial')
    parser.add_argument('--horizon', type=int, choices=[1,3,5,15,60], default=3)
    parser.add_argument('--alpha', type=float, default=10.)
    parser.add_argument('--chunk-size', type=int, default=4096)
    parser.add_argument('--output', type=Path, default=Path('data/research-v16'))
    args = parser.parse_args()
    try:
        from train_v15 import timestamp
        directory, report = run_training(args.files, args.venue, args.symbol, args.output,
            timestamp(args.train_end), timestamp(args.calibration_end), timestamp(args.test_end),
            args.model, args.horizon, args.alpha, args.chunk_size)
        print(f'Completed: {directory}\nModel remains research-only and unapproved.')
        print(json.dumps(report['holdout'], indent=2))
        return 0
    except KeyboardInterrupt:
        print('\nInterrupted. Rerun the same command; completed fits are reused.', file=sys.stderr)
        return 130
    except ImportError as error:
        print(f'Dependency unavailable: {error}. Activate the virtual environment and run python -m pip install -r requirements.txt', file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, MemoryError) as error:
        print(f'Training stopped: {type(error).__name__}: {error}. Check data, dates, disk space, and the run status.json. For memory errors, reduce --chunk-size.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
