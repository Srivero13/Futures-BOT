"""Consolidate disjoint saved evaluations of one unchanged frozen pack."""
import argparse
import json
import math
from pathlib import Path
from engine_v1.dataset import sha256
from engine_v1.operations import atomic_json


def number(value):
    x=float(value)
    if not math.isfinite(x):raise ValueError('Non-finite metric')
    return x


def count(value):
    if type(value) is not int or value<0:raise ValueError('Invalid count')
    return value


def consolidate(pack,pack_hash,reports):
    if pack['kind']!='frozen_feature_pack_v1':raise ValueError('Unsupported pack')
    if not reports:raise ValueError('No reports found')
    names=set(pack['models']);seen=set();intervals=[];total=0;zero_sse=0.;monthly=[]
    totals={name:dict(sse=0.,selected=0,selected_sum=0.,eligible=0,wins_zero=0,wins_baseline=0) for name in names}
    for report in reports:
        if report['pack_sha256']!=pack_hash:raise ValueError('Reports use a different frozen pack')
        source=report['evaluation'];capture=source['flow']['capture']
        if source['dynamics']['capture']!=capture or capture in seen:raise ValueError('Duplicate or mismatched capture')
        seen.add(capture)
        starts=[];ends=[]
        for key in ('dynamics','flow'):
            p=source[key];training=pack['training'][key]
            start=count(p['first_decision_wall_ns']);end=count(p['last_label_wall_ns_estimate'])
            if end<=start or start<=max(pack['frozen_at_wall_ns'],training['last_label_wall_ns_estimate']):raise ValueError('Invalid evaluation chronology')
            if p['capture']==training['capture'] or p['builder_code_sha256']!=training['builder_code_sha256']:raise ValueError('Invalid evaluation provenance')
            starts.append(start);ends.append(end)
        intervals.append((min(starts),max(ends)))
        s=report['summary'];n=count(s['counts']['common_rows'])
        if n==0 or n>min(count(s['counts']['dynamics_rows']),count(s['counts']['flow_rows'])):raise ValueError('Invalid paired count')
        if set(s['models'])!=names:raise ValueError('Model set differs')
        zero=number(s['zero_rmse_log_bps'])
        if zero<0:raise ValueError('Negative RMSE')
        total+=n;zero_sse+=n*zero**2
        base=number(s['models']['baseline']['rmse_log_bps'])
        for name,m in s['models'].items():
            if number(m['frozen_top_cutoff_log_bps'])!=number(pack['models'][name]['top_cutoff']):raise ValueError('Frozen cutoff differs')
            rmse=number(m['rmse_log_bps']);selected=count(m['selected_samples']);eligible=count(m['cost_eligible_forecasts'])
            if rmse<0 or not eligible<=selected<=n:raise ValueError('Invalid model metrics')
            mean=m['selected_mean_quote_log_bps']
            if selected==0 and mean is not None:raise ValueError('Empty selection has a mean')
            t=totals[name];t['sse']+=n*rmse**2;t['selected']+=selected
            t['selected_sum']+=selected*number(mean) if selected else 0
            t['eligible']+=eligible;t['wins_zero']+=int(rmse<zero);t['wins_baseline']+=int(rmse<base)
        monthly.append({'capture':capture,'first_decision_wall_ns':min(starts),'common_rows':n,'models':s['models']})
    ordered=sorted(intervals)
    if any(b[0]<=a[1] for a,b in zip(ordered,ordered[1:])):raise ValueError('Overlapping evaluation intervals')
    summary={'captures':len(reports),'common_rows':total,'pooled_zero_rmse_log_bps':math.sqrt(zero_sse/total),'models':{}}
    for name,t in sorted(totals.items()):
        summary['models'][name]={'pooled_rmse_log_bps':math.sqrt(t['sse']/total),
            'captures_beating_zero':t['wins_zero'],'captures_beating_baseline':t['wins_baseline'],
            'selected_samples':t['selected'],'selected_weighted_mean_quote_log_bps':t['selected_sum']/t['selected'] if t['selected'] else None,
            'cost_eligible_forecasts':t['eligible']}
    return summary,sorted(monthly,key=lambda r:r['first_decision_wall_ns'])


def run(pack_path,paths,output):
    if output.exists():raise ValueError('Output exists; choose a new filename')
    digest=sha256(pack_path);pack=json.loads(pack_path.read_text());reports=[];sources=[]
    for path in paths:
        h=sha256(path);reports.append(json.loads(path.read_text()))
        if sha256(path)!=h:raise ValueError('Report changed while loading')
        sources.append({'path':str(path.resolve()),'sha256':h})
    summary,details=consolidate(pack,digest,reports)
    if sha256(pack_path)!=digest:raise ValueError('Pack changed')
    atomic_json(output,{'approved':False,'pnl':None,'summary':summary,'captures':details,'sources':sources,
        'pack_sha256':digest,'symbol':pack['symbol'],'frozen_cost_barrier_log_bps':pack['cost_barrier_log_bps'],
        'runner_sha256':sha256(Path(__file__)),
        'limitations':['Consolidates saved report statistics; does not replay or independently recompute raw predictions.',
        'RMSE pooled through sample-weighted squared errors; selected means weighted by selected counts.',
        'Spearman values remain per capture; correlations are not pooled or averaged.',
        'Disjoint time intervals do not imply statistical independence. No significance or portfolio P&L claim.',
        'Fees and slippage remain frozen hypothetical assumptions, not verified account rates.']})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pack',required=True,type=Path);p.add_argument('--reports',required=True,nargs='+',type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    try:print(json.dumps(run(a.pack,a.reports,a.output),indent=2))
    except (ValueError,OSError,KeyError,TypeError) as e:p.exit(2,f'Summary stopped: {e}\n')


if __name__=='__main__':main()
