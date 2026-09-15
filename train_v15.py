"""Train/evaluate one venue and symbol from verified chronological shards."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
try:
    import resource
except ImportError:
    resource = None
import time
from engine_v1.dataset import examples, sha256
from engine_v1.operations import atomic_json
from engine_v1.training import fit_stream, evaluate_stream


def timestamp(value):
    return int(datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)


def run(paths, venue, symbol, output, train_end, calibration_end, test_end, chunk_size=8192, compiled=False):
    if not 0 < train_end < calibration_end < test_end:
        raise ValueError('Invalid chronological split')
    output.mkdir(parents=True, exist_ok=True)
    sources = []
    for path in paths:
        digest = sha256(path)
        meta_path = path.with_suffix('.json')
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else None
        legacy_path = path.parent / 'manifest-v1.1.json'
        if meta is None and legacy_path.exists():
            legacy = json.loads(legacy_path.read_text())
            record = legacy.get(symbol, {})
            if record.get('sha256') == digest and venue == 'binance':
                meta = {**record, 'venue': venue, 'symbol': symbol, 'timeframe_ms': 60000,
                        'archives': [a for a in legacy['archives'] if '/' + symbol + '/' in a['url']]}
        if meta and (meta['sha256'] != digest or meta['venue'] != venue or meta['symbol'] != symbol or meta['timeframe_ms'] != 60000):
            raise ValueError('Shard integrity or source identity mismatch')
        sources.append({'file': path.name, 'bytes': path.stat().st_size, 'sha256': digest,
                        'provenance': meta or 'Local canonical CSV; venue identity supplied by operator'})
    started = time.perf_counter()
    factory = lambda: examples(paths, horizon=3, chunk_size=chunk_size)
    model, calibration = fit_stream(factory, symbol, 3, train_end, calibration_end)
    metrics = evaluate_stream(factory, model, calibration_end, test_end, compiled=compiled)
    # Fail if inputs changed during the multipass experiment.
    for path, source in zip(paths, sources):
        if sha256(path) != source['sha256']:
            raise ValueError('Dataset changed during training')
    model_path = output / f'{venue}-{symbol}.json'
    temporary_model = model_path.with_suffix('.partial')
    model.save(temporary_model)
    temporary_model.replace(model_path)
    report = {'version': '1.5', 'venue': venue, 'symbol': symbol, 'sources': sources,
              'input_bytes': sum(s['bytes'] for s in sources), 'chunk_size': chunk_size,
              'inference_backend': 'numba' if compiled else 'numpy',
              'fit_rows': model.fit_rows, 'calibration_rows': model.calibration_rows,
              'calibration': calibration, 'holdout': metrics,
              'seconds': time.perf_counter() - started,
              'peak_rss_kib_linux': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None,
              'approved': False, 'train_end_ms': train_end, 'calibration_end_ms': calibration_end,
              'test_end_ms': test_end}
    atomic_json(output / f'{venue}-{symbol}-evaluation.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--files', nargs='+', type=Path, required=True, help='Chronological, non-overlapping canonical CSV or CSV.gz files')
    p.add_argument('--venue', required=True)
    p.add_argument('--symbol', required=True)
    p.add_argument('--train-end', required=True)
    p.add_argument('--calibration-end', required=True)
    p.add_argument('--test-end', required=True)
    p.add_argument('--chunk-size', type=int, default=8192)
    p.add_argument('--compiled', action='store_true', help='Use optional Numba batch inference for holdout evaluation')
    p.add_argument('--output', type=Path, default=Path('data/research-v15'))
    a = p.parse_args()
    import re
    if not all(re.fullmatch(r'[A-Za-z0-9_-]{1,32}', v) for v in (a.venue, a.symbol)):
        p.error('Invalid venue or symbol identifier')
    result = run(a.files, a.venue, a.symbol, a.output, timestamp(a.train_end), timestamp(a.calibration_end), timestamp(a.test_end), a.chunk_size, a.compiled)
    print(json.dumps({k: v for k, v in result.items() if k != 'sources'}, indent=2))


if __name__ == '__main__':
    main()
