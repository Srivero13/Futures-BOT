"""Local operational controls. No broker credentials or execution endpoints."""
import argparse
from contextlib import contextmanager,closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def atomic_json(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(payload,f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


@contextmanager
def process_lock(path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        f.seek(0)
        if os.name=='nt':
            import msvcrt
            if not f.read(1):f.write(b'0');f.flush()
            f.seek(0)
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Another coordinator owns this database') from None
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise RuntimeError('Another coordinator owns this database') from None
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)


def backup_database(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if source==destination or destination.exists():raise ValueError('Backup destination must be a new file')
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=destination.parent,suffix='.sqlite3');os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(tmp)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed')
        # Hard-link publication refuses overwrite even if another process races us.
        os.link(tmp,destination)
    finally:os.unlink(tmp)


def read_status(path,max_age_seconds=15):
    value=json.loads(Path(path).read_text());age=time.time()*1000-value['timestamp_ms']
    value['heartbeat_age_ms']=age
    value['heartbeat_current']=0<=age<=max_age_seconds*1000 and value.get('running',False)
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    status=sub.add_parser('status');status.add_argument('--file',default='data/health.json')
    backup=sub.add_parser('backup');backup.add_argument('database');backup.add_argument('destination')
    a=p.parse_args()
    if a.command=='status':print(json.dumps(read_status(a.file),indent=2))
    else:backup_database(a.database,a.destination);print('Verified database backup created.')
if __name__=='__main__':main()
