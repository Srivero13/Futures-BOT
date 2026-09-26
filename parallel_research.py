"""Run fixed CPU polynomial and CUDA neural development jobs concurrently."""
import argparse
import os
from pathlib import Path
import sys
from engine_v1.operations import atomic_json
from engine_v1.processes import run_workers


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--worker-timeout-seconds',type=float,default=3600,
                   help='Deadline per monthly CPU/GPU pair, excluding CUDA preflight (default: 3600)')
    a=p.parse_args();source=Path(__file__).resolve().parent
    import math
    if not math.isfinite(a.worker_timeout_seconds) or a.worker_timeout_seconds<=0:
        raise ValueError('Worker timeout must be finite and positive')
    # Exercise real CUDA allocation, forward/backward and optimization before launch.
    from engine_v1.research_mlp import fit_predict
    import numpy as np
    import torch
    x=np.random.default_rng(1729).normal(size=(128,3))
    fit_predict(x,x[:,0],[x[:5]],epochs=1)
    if a.output_dir.exists():raise ValueError('Use a new output directory')
    for month in range(3,9):
        if not (a.audit_dir/f'ETHUSDT-2026-{month:02d}-alignment.json').is_file():
            raise ValueError('Missing monthly alignment report')
    a.output_dir.mkdir(parents=True)
    atomic_json(a.output_dir/'protocol.json',{'approved':False,'test_months':['2026-05','2026-06','2026-07','2026-08'],
        'cpu':'polynomial ridge alpha=10','gpu':'MLP 32/16, 40 epochs, seed 1729',
        'torch':torch.__version__,'cuda':torch.version.cuda,'gpu_name':torch.cuda.get_device_name(0),
        'worker_timeout_seconds':a.worker_timeout_seconds,
        'note':'Already inspected development periods. No promotion or trading.'})
    env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
    for month in range(5,9):
        jobs=[]
        for backend in ('polynomial','cuda-mlp'):
            log=a.output_dir/f'{month:02d}-{backend}.log'
            cmd=[sys.executable,'-u',str(source/'evaluate_tradeflow.py'),'--audits',
                *[str(a.audit_dir/f'ETHUSDT-2026-{m:02d}-alignment.json') for m in range(month-2,month+1)],
                '--symbol','ETHUSDT','--start',f'2026-{month-2:02d}-01','--reserve-from','2026-09-01',
                '--backend',backend,'--output',str(a.output_dir/f'{month:02d}-{backend}.json')]
            jobs.append({'name':backend,'argv':cmd,'log':log})
            print(f'[parallel] month={month} backend={backend} log={log}',flush=True)
        run_workers(jobs,a.output_dir/f'{month:02d}-workers.json',a.worker_timeout_seconds,env=env)
        print(f'[parallel] month={month} both workers complete',flush=True)
    print(f'Completed: {a.output_dir}; eight reports, research-only.',flush=True)


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,ImportError,OSError) as error:
        print(f'Parallel research stopped: {error}',file=sys.stderr);raise SystemExit(2)
    except KeyboardInterrupt:raise SystemExit(130)
