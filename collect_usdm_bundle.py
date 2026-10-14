"""Resumable bounded ETHUSDT development data acquisition; never trades."""
import argparse
from datetime import date,datetime,timedelta,timezone
import json
from pathlib import Path
from audit_usdm_pilot import audit as audit_trades
from audit_usdm_funding import audit as audit_funding
from batch_usdm_marks import audit_marks
from download_usdm_pilot import download as download_trades
from download_usdm_marks import download as download_marks
from download_usdm_funding import download as download_funding
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json,process_lock


def run(start,end,spot,output):
    reserve=date(2026,9,1)
    if not 1<=(end-start).days<=31 or end>reserve or end>datetime.now(timezone.utc).date():
        raise ValueError('Require 1–31 completed development days before reserve')
    spot,output=Path(spot),Path(output)
    days=[start+timedelta(days=i) for i in range((end-start).days)]
    for day in days:
        shard=spot/f'binance-ETHUSDT-{day:%Y-%m}.csv'
        if not shard.is_file() or not shard.with_suffix('.json').is_file():
            raise ValueError(f'Missing spot input: {shard}')
    output.parent.mkdir(parents=True,exist_ok=True)
    identity=dict(symbol='ETHUSDT',start=str(start),end_exclusive=str(end),reserve_from=str(reserve),
                  spot_root=str(spot.resolve()),format_version=1)
    with process_lock(str(output)+'.lock'):
        manifest=output/'bundle.json'
        if output.exists() or output.is_symlink():
            if output.is_symlink() or not manifest.is_file():
                raise ValueError('Existing output is not a recognized bundle')
            old=json.loads(manifest.read_text())
            if old.get('identity')!=identity:
                raise ValueError('Resume identity mismatch')
        else:
            output.mkdir()
        status=dict(approved=False,identity=identity,status='running',completed_days=[],funding_chunks=[],
                    runner_sha256=sha256(Path(__file__)))
        atomic_json(manifest,status)
        hashes={}
        def retain(report):
            for path,h in report['inputs_sha256'].items():
                if path in hashes and hashes[path]!=h: raise ValueError('Shared input changed')
                hashes[path]=h
        try:
            for i,day in enumerate(days,1):
                print(f'[bundle] day {i}/{len(days)}: {day}',flush=True)
                folder=output/'trades'/str(day)
                if not folder.exists(): download_trades('ETHUSDT',day,reserve,folder)
                a=audit_trades(folder,spot/f'binance-ETHUSDT-{day:%Y-%m}.csv','ETHUSDT',day,reserve)
                if a.get('matched_minutes')!=1440 or not all(a.get(k) is True for k in ('integrity_passed','archive_conversion_equal','timestamp_alignment_passed')):
                    raise ValueError('Trade audit failed')
                retain(a)
                folder=output/'marks'/str(day)
                if not folder.exists(): download_marks('ETHUSDT',day,reserve,folder)
                a=audit_marks(folder,day)
                if a.get('rows')!=1440 or a.get('integrity_passed') is not True: raise ValueError('Mark audit failed')
                retain(a)
                status['completed_days'].append(str(day));atomic_json(manifest,status)
            cursor=start
            while cursor<end:
                stop=min(cursor+timedelta(days=7),end)
                folder=output/'funding'/str(cursor)
                print(f'[bundle] funding {cursor} to {stop} exclusive',flush=True)
                if not folder.exists(): download_funding('ETHUSDT',cursor,stop,reserve,folder)
                a=audit_funding(folder,'ETHUSDT',cursor,stop,reserve)
                if a.get('integrity_passed') is not True or a.get('raw_conversion_equal') is not True:
                    raise ValueError('Funding audit failed')
                retain(a)
                status['funding_chunks'].append(dict(start=str(cursor),end_exclusive=str(stop),records=a['records']))
                atomic_json(manifest,status);cursor=stop
            if any(sha256(p)!=h for p,h in hashes.items()): raise ValueError('Input changed before completion')
            status.update(status='complete',minutes=len(days)*1440,inputs_sha256=hashes,schedule_coverage_verified=False)
            atomic_json(manifest,status)
        except BaseException as error:
            status.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',error_type=type(error).__name__)
            try: atomic_json(manifest,status)
            except Exception as failure: error.add_note(f'Could not save status: {type(failure).__name__}')
            raise
    return status


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('start','end'): p.add_argument('--'+name,type=date.fromisoformat,required=True)
    p.add_argument('--spot-root',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args();r=run(a.start,a.end,a.spot_root,a.output_dir)
    print(json.dumps({k:v for k,v in r.items() if k!='inputs_sha256'},indent=2))


if __name__=='__main__': main()
