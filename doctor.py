"""Offline startup diagnostics. Uses the standard library before checking dependencies."""
import argparse
import importlib
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile


def check(root, output):
    results = []
    def record(name, ok, detail):
        results.append({'check': name, 'ok': bool(ok), 'detail': detail})
    record('python', sys.version_info[:2] == (3, 12), f'{platform.python_version()}; documented/tested target is Python 3.12')
    available = True
    for module, package in [('numpy', 'numpy'), ('websocket', 'websocket-client')]:
        try:
            imported = importlib.import_module(module)
            version = getattr(imported, '__version__', '')
            valid = version == '1.8.0' if module == 'websocket' else version == '2.3.5'
            record(package, valid, f'{version}; reinstall requirements.txt if this check fails')
            available = available and valid
        except (ImportError, OSError) as error:
            available = False
            record(package, False, f'{type(error).__name__}; run python -m pip install -r requirements.txt in the active environment')
    try:
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=output) as handle:
            handle.write(b'preflight'); handle.flush()
        free = shutil.disk_usage(output).free
        record('output_disk', free >= 1024**3, f'{free/1024**3:.1f} GiB free; minimum reserve is 1 GiB')
    except OSError as error:
        record('output_disk', False, str(error))
    if available:
        try:
            from engine_v1.model import feature_matrix
            from engine_v1.nonlinear import load_model
            from engine_v1.core import Portfolio
            import numpy as np
            rows = [{'close':'100', 'high':'101', 'low':'99', 'volume':'10'} for _ in range(21)]
            if not np.isfinite(feature_matrix(rows)[-1]).all():
                raise ValueError('Feature smoke test failed')
            cfg = json.loads((root/'configs/v11-paper.json').read_text())
            if cfg['mode'] != 'paper': raise ValueError('Only paper configuration is supported')
            for account in cfg['accounts']:
                model = load_model(root/cfg['model_directory']/f"{account['symbol']}-v1.json")
                if model.symbol != account['symbol']: raise ValueError('Model symbol mismatch')
            portfolio = Portfolio(':memory:', cfg['accounts'], **cfg['risk'])
            portfolio.close()
            record('offline_smoke', True, 'Features, model checksums and in-memory paper ledger passed; no orders sent')
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
            record('offline_smoke', False, str(error))
    return {'version':'1.6', 'ready':all(r['ok'] for r in results), 'checks':results,
            'scope':'Offline checks only. Does not certify network access, hardware stability, clock sync, strategy quality or unattended operation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('data'))
    args = parser.parse_args()
    result = check(Path(__file__).resolve().parent, args.output_dir)
    print(json.dumps(result, indent=2))
    return 0 if result['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
