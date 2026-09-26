"""Bounded supervision of explicitly supplied local research subprocesses."""
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from .operations import atomic_json


class WorkerFailure(RuntimeError):
    pass


def stop_workers(children, grace_seconds):
    """Stop only our child processes (and their groups on POSIX), then reap them."""
    def send(child, sig):
        try:
            if os.name == 'posix':
                os.killpg(child.pid, sig)
            elif child.poll() is None:
                child.terminate() if sig == signal.SIGTERM else child.kill()
        except ProcessLookupError:
            pass

    for child in children:
        send(child, signal.SIGTERM)
    deadline = time.monotonic()+grace_seconds
    for child in children:
        try:
            child.wait(timeout=max(0, deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    # Signal groups even if their direct parent has exited; descendants may remain.
    for child in children:
        send(child, getattr(signal, 'SIGKILL', signal.SIGTERM))
    for child in children:
        child.wait(timeout=5)


def run_workers(jobs, status_path, timeout_seconds, env=None, cwd=None,
                poll_seconds=.2, heartbeat_seconds=5., grace_seconds=5.):
    """Jobs contain name, argv and log. No shell, restart or model approval."""
    for value in (timeout_seconds, poll_seconds, heartbeat_seconds, grace_seconds):
        if not math.isfinite(value) or value <= 0:
            raise ValueError('Supervisor timing values must be finite and positive')
    names = [job['name'] for job in jobs]
    logs = [Path(job['log']).resolve() for job in jobs]
    status_path = Path(status_path).resolve()
    if not jobs or len(set(names)) != len(names) or len(set(logs)) != len(logs):
        raise ValueError('Require unique worker names and logs')
    if status_path in logs or status_path.exists() or any(p.exists() for p in logs):
        raise ValueError('Status and log paths must be distinct new files')
    if any(not isinstance(job['argv'], list) or not job['argv'] or
           any(not isinstance(arg, str) or not arg for arg in job['argv']) for job in jobs):
        raise ValueError('Require nonempty argv lists of strings')
    children, handles = [], []
    began = time.monotonic()
    state, reason = 'starting', None
    old_handlers = {}

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM,):
            old_handlers[sig] = signal.signal(sig, interrupted)

    def publish():
        atomic_json(status_path, {
            'approved': False, 'state': state, 'reason': reason,
            'updated_at_utc': datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds': time.monotonic()-began,
            'timeout_seconds': timeout_seconds,
            'supervisor_pid': os.getpid(),
            'workers': [{'name': name, 'pid': children[i].pid if i < len(children) else None,
                         'returncode': children[i].poll() if i < len(children) else None,
                         'log': str(logs[i])} for i, name in enumerate(names)],
            'note': 'Process status only; successful exit does not certify research outputs or profitability.'})

    try:
        publish()
        for job, log in zip(jobs, logs):
            log.parent.mkdir(parents=True, exist_ok=True)
            handle = log.open('x')
            handles.append(handle)
            children.append(subprocess.Popen(job['argv'], stdout=handle, stderr=subprocess.STDOUT,
                env=env, cwd=cwd, start_new_session=(os.name == 'posix')))
        state = 'running'
        publish()
        next_heartbeat = time.monotonic()+heartbeat_seconds
        while True:
            codes = [child.poll() for child in children]
            if any(code is not None and code != 0 for code in codes):
                state, reason = 'failed', 'worker_nonzero_exit'
                raise WorkerFailure('Research worker failed; inspect the status file and worker logs')
            if all(code is not None for code in codes):
                state = 'succeeded'
                break
            now = time.monotonic()
            if now-began >= timeout_seconds:
                state, reason = 'timed_out', 'worker_pair_deadline'
                raise WorkerFailure('Research worker deadline exceeded; workers stopped')
            if now >= next_heartbeat:
                publish()
                print(f'[workers] elapsed={now-began:.0f}s running={sum(c is None for c in codes)}/{len(codes)}', flush=True)
                next_heartbeat = now+heartbeat_seconds
            time.sleep(min(poll_seconds, max(0, timeout_seconds-(now-began))))
    except KeyboardInterrupt:
        state, reason = 'interrupted', 'operator_interrupt'
        raise
    except BaseException:
        if state not in ('failed', 'timed_out'):
            state, reason = 'failed', 'supervisor_or_launch_error'
        raise
    finally:
        try:
            stop_workers(children, grace_seconds)
        except BaseException:
            state, reason = 'failed', 'cleanup_error'
            raise
        finally:
            for handle in handles:
                handle.close()
            try:
                publish()
            finally:
                for sig, handler in old_handlers.items():
                    signal.signal(sig, handler)
    return [child.returncode for child in children]
