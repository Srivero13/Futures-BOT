"""Replay frozen delayed quote forecasts with fixed costs; no orders or approval."""
import argparse
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json
from diagnose_execution_microstructure import Diagnostic
from replay_market import replay
from train_delayed_microstructure import FEATURES, SETTINGS


def cost_barrier():
    # Target already includes spread. Fees apply to both fill notionals.
    with localcontext() as ctx:
        ctx.prec=50
        slip=Decimal('0.0002');fee=Decimal('0.001')
        ratio=(1+slip)*(1+fee)/((1-slip)*(1-fee))
        return float(ratio.ln()*10000)


class DelayedDiagnostic(Diagnostic):
    def __init__(self,model,gated):
        super().__init__(model)
        self.training_threshold=self.threshold
        if not math.isfinite(self.threshold):raise ValueError('Non-finite training cutoff')
        self.gated=gated
        if gated:self.threshold=max(self.threshold,cost_barrier())

    def summary(self):
        result=super().summary()
        result['training_top_bucket_threshold_log_bps']=self.training_threshold
        result['effective_entry_threshold_log_bps']=self.threshold
        result['cost_gate_enabled']=self.gated
        result['cost_barrier_log_bps']=cost_barrier()
        return result


def run(capture,model_path,output):
    capture=Path(capture).resolve();model_path=Path(model_path);output=Path(output)
    if output.exists():raise ValueError('Output exists; choose a new directory')
    digest=sha256(model_path);model=json.loads(model_path.read_text())
    if (model['kind']!='delayed_microstructure_research_ridge' or model['features']!=FEATURES
            or model['settings']!=SETTINGS or model['alpha']!=10):raise ValueError('Unsupported delayed model')
    root=Path(__file__).parent
    if model['runner_sha256']!=sha256(root/'train_delayed_microstructure.py'):raise ValueError('Training code changed')
    if str(capture)==model['training']['capture']:raise ValueError('Development capture is not evaluation')
    for name,expected in model['training']['builder_code_sha256'].items():
        if Path(name).name!=name or sha256(root/name)!=expected:raise ValueError('Sampling code changed')
    current=json.loads((capture/'protocol.json').read_text())
    training=json.loads((Path(model['training']['capture'])/'protocol.json').read_text())
    if current['symbol']!=training['symbol']:raise ValueError('Capture symbols differ')
    engines={name:DelayedDiagnostic(model,gated) for name,gated in [('top_bucket',False),('cost_gated',True)]}
    output.mkdir(parents=True)
    def accept(record,quote):
        if quote is not None and 'receipt_wall_ns' not in record:raise ValueError('Missing quote wall time')
        for engine in engines.values():engine.accept(record,quote)
    replay(capture,output/'replay-verification.json',on_quote=accept)
    for engine in engines.values():engine.reset('end')
    if sha256(model_path)!=digest:raise ValueError('Model changed during replay')
    summaries={name:engine.summary() for name,engine in engines.items()}
    limitations=['Retrospective diagnostic on previously inspected data; not a new holdout.',
        'Cost gate compares a mean log-return forecast with a deterministic break-even barrier; not a confidence bound or expected-profit guarantee.',
        'Spread is already in the target and is not added again to the barrier.',
        'Fixed 100 quote-unit entries, fee 10 bps and adverse slippage 2 bps per side. Hypothetical assumptions, not verified account rates.',
        'Receipt-time entry delay 500 ms and hold 5 seconds with 250 ms lateness; no additional exit-order latency.',
        'Displayed top depth does not guarantee fills; no exchange filters, quantity rounding or queue modeling.',
        'Unresolved positions remain excluded. Each engine continues diagnostics after such boundaries; this is not portfolio P&L.',
        'Independent engine schedules can diverge after entries. Do not treat their difference as a paired causal estimate.',
        'No orders, parameter tuning, model approval, or profitability certification.']
    protocol={'model_sha256':digest,'capture':str(capture),'entry_delay_ms':500,'holding_ms_after_entry':5000,
        'fee_bps_per_side':10,'slippage_bps_per_side':2,'notional':'100','approved':False,
        'code_sha256':{name:sha256(root/name) for name in ('diagnose_delayed_execution.py','diagnose_execution_microstructure.py','replay_market.py','train_delayed_microstructure.py')}}
    for name,engine in engines.items():
        atomic_json(output/(name+'.json'),{'approved':False,'protocol':protocol,'summary':summaries[name],
            'closed_trades':engine.trades,'limitations':limitations,'replay_sha256':sha256(output/'replay-verification.json')})
    atomic_json(output/'summary.json',{'approved':False,'summary':summaries,'protocol':protocol,'limitations':limitations})
    return summaries


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('capture','model','output-dir'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    try:print(json.dumps(run(a.capture,a.model,a.output_dir),indent=2))
    except (ValueError,OSError,KeyError,TypeError) as error:p.exit(2,f'Delayed execution stopped: {error}\n')


if __name__=='__main__':main()
