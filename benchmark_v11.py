"""Compare v1.0 and v1.1 on identical local CPU and idle-ledger workloads."""
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import numpy as np
from engine_v1 import core,model
from engine_v1.operations import atomic_json
from train_v1 import load_rows
ROOT=Path(__file__).resolve().parent
BASE='58590544fa26f55390baaa41d7aab953e611a094'


def old_module(name,path,directory):
    source=subprocess.check_output(['git','show',f'{BASE}:{path}'],cwd=ROOT,text=True)
    destination=Path(directory)/(name+'.py');destination.write_text(source)
    spec=importlib.util.spec_from_file_location(name,destination);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module


def ledger_case(module,path,n=10000):
    accounts=[{'id':'a','symbol':'BTCUSDT','capital':'1000','notional':'100'}]
    p=module.Portfolio(path,accounts);t0=time.perf_counter()
    for i in range(n):
        q=module.Quote('BTCUSDT',module.dec('100'),module.dec('100'),module.dec('10'),module.dec('10'),i*1000,i)
        p.process({'BTCUSDT':q},{},i*1000,event_id=str(i))
    elapsed=time.perf_counter()-t0;count=p.db.execute('SELECT count(*) FROM events').fetchone()[0]
    p.close()
    return {'idle_ticks':n,'elapsed_seconds':elapsed,'events_rows':count,'database_bytes_after_close':Path(path).stat().st_size}


def main():
    rows=load_rows(ROOT/'datasets/BTCUSDT-1m-2025Q2Q3.csv')[:10000]
    report={'baseline_commit':BASE,'python':platform.python_version(),'numpy':np.__version__,
        'location':'development runtime, not the i7/ENTEL PC','feature_rows':len(rows),'repeats':3,'features':{},'idle_ledger':{}}
    with tempfile.TemporaryDirectory() as tmp:
        old_model=old_module('baseline_model','engine_v1/model.py',tmp)
        old_core=old_module('baseline_core','engine_v1/core.py',tmp)
        for name,module in [('v1.0',old_model),('v1.1',model)]:
            durations=[]
            for _ in range(3):
                t0=time.perf_counter();x=module.feature_matrix(rows);durations.append(time.perf_counter()-t0)
            report['features'][name]={'seconds':durations,'median_seconds':statistics.median(durations)}
            if name=='v1.0':baseline=x
            else:np.testing.assert_allclose(baseline,x,rtol=1e-10,atol=1e-12,equal_nan=True)
        report['feature_speedup']=report['features']['v1.0']['median_seconds']/report['features']['v1.1']['median_seconds']
        report['idle_ledger']['v1.0']=ledger_case(old_core,Path(tmp)/'old.sqlite3')
        report['idle_ledger']['v1.1']=ledger_case(core,Path(tmp)/'new.sqlite3')
    report['note']='Same rows and host. Feature equivalence checked. No trading-latency or profitability claim. Ledger includes SQLite I/O and one account; trade audit records are retained.'
    atomic_json(ROOT/'reports/v1.1/benchmark.json',report);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
