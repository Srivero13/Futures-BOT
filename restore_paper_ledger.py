"""Restore a SQLite paper backup to a new path while preserving all ledger state."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from engine_v1.operations import backup_database, process_lock


def inspect_ledger(path):
    """Check expected schema and JSON containers; not a financial reconciliation."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('Backup failed SQLite integrity check')
        fingerprints=db.execute('SELECT id,fingerprint FROM config').fetchall()
        if len(fingerprints)!=1 or fingerprints[0][0]!=1:
            raise ValueError('Invalid ledger configuration')
        fingerprint=fingerprints[0][1]
        if not isinstance(fingerprint,str) or len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint):
            raise ValueError('Invalid configuration fingerprint')
        accounts=db.execute('SELECT id,state FROM accounts ORDER BY id').fetchall()
        if not accounts: raise ValueError('Backup has no accounts')
        for account,state in accounts:
            value=json.loads(state)
            if not isinstance(value,dict) or value.get('id')!=account:
                raise ValueError('Invalid account state')
        risk=db.execute('SELECT id,state FROM risk').fetchall()
        if len(risk)!=1 or risk[0][0]!=1 or not isinstance(json.loads(risk[0][1]),dict):
            raise ValueError('Invalid risk state')
        # Require the current deduplication and event columns even for empty tables.
        db.execute('SELECT account,event,timestamp_ms FROM processed LIMIT 0')
        db.execute('SELECT id,timestamp_ms,account,payload FROM events LIMIT 0')
        return {'accounts':len(accounts),'events':db.execute('SELECT count(*) FROM events').fetchone()[0],
                'processed_events':db.execute('SELECT count(*) FROM processed').fetchone()[0],
                'configuration_fingerprint':fingerprint}


def restore(source,destination):
    source=Path(source).resolve()
    raw_destination=Path(destination).absolute()
    if raw_destination.is_symlink():
        raise ValueError('Destination must not be a symlink')
    destination=raw_destination.resolve()
    if not source.is_file() or source==destination:
        raise ValueError('Provide an existing backup and a distinct new destination')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Uses the same lock names as the coordinator. Never restore into an active ledger.
    with process_lock(str(source)+'.lock'), process_lock(str(destination)+'.lock'):
        if any(Path(str(destination)+suffix).exists() for suffix in ('','-wal','-shm','-journal')):
            raise ValueError('Destination or SQLite sidecar already exists; choose a new path')
        with tempfile.TemporaryDirectory(prefix='ledger-restore-',dir=destination.parent) as tmp:
            snapshot=Path(tmp)/'snapshot.sqlite3'
            backup_database(source,snapshot)
            details=inspect_ledger(snapshot)
            # Atomic no-overwrite publication. Existing source/backup is never replaced.
            os.link(snapshot,destination)
    return {'restored':str(destination),'source':str(source),'approved':False,**details,
            'note':'State preserved; bot remains stopped. Integrity/schema checks are not a financial audit.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',required=True,type=Path)
    parser.add_argument('--destination',required=True,type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(restore(args.backup,args.destination),indent=2))
    except (ValueError,OSError,sqlite3.Error,RuntimeError) as error:
        parser.exit(2,f'Restore stopped: {error}\n')


if __name__=='__main__':main()
