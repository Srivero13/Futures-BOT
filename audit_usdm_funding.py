"""Saved funding integrity and explicit reference-grid diagnostics; no approval."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from download_usdm_funding import ENDPOINT, LIMIT, timestamp, validate_page
from engine_v1.dataset import sha256


def grid_diagnostic(records, start, end, tolerance=1000):
    """Fixed UTC 00/08/16 reference only. Never change settlement timestamps."""
    step = 8*3600*1000
    slots = {t: [] for t in range(start, end, step)}
    outside = []
    offsets = []
    for row in records:
        t = row['funding_time_ms']
        nearest = ((t+step//2)//step)*step
        offset = t-nearest
        if nearest not in slots or abs(offset) > tolerance:
            outside.append(t)
        else:
            slots[nearest].append(t)
            offsets.append(offset)
    missing = [t for t, events in slots.items() if not events]
    duplicate = [t for t, events in slots.items() if len(events)>1]
    return {'reference_interval_hours': 8, 'reference_tolerance_ms': tolerance,
            'expected_reference_slots': len(slots), 'matched_events': len(offsets),
            'missing_reference_slots_ms': missing, 'duplicate_reference_slots_ms': duplicate,
            'off_grid_events_ms': outside,
            'max_absolute_offset_ms': max(map(abs, offsets), default=None),
            'reference_grid_complete': not (missing or duplicate or outside)}


def audit(root, symbol, start, end, reserve):
    root = Path(root)
    if not re.fullmatch(r'[A-Z0-9]{3,24}', symbol) or not 1 <= (end-start).days <= 7 or end > reserve:
        raise ValueError('Invalid symbol, range or reserve')
    summary = root/'summary.json'
    before = {str(summary.resolve()): sha256(summary)}
    m = json.loads(summary.read_text())
    expected = dict(venue='binance_usdm', kind='funding_history', symbol=symbol,
                    start=str(start), end_exclusive=str(end))
    if any(m.get(k)!=v for k,v in expected.items()) or m.get('approved') is not False:
        raise ValueError('Funding metadata identity mismatch')
    if end > date.fromisoformat(m['reserve_from']) or date.fromisoformat(m['reserve_from']) > reserve:
        raise ValueError('Saved reserve mismatch')
    pages = m['pages']
    if not isinstance(pages, list) or not 1 <= len(pages) <= 8:
        raise ValueError('Invalid page manifest')
    cursor, stop = timestamp(start), timestamp(end)
    records = []
    exhausted = False
    for n, item in enumerate(pages):
        name = f'page-{n:02d}.json'
        url = ENDPOINT+'?'+urlencode(dict(symbol=symbol,startTime=cursor,endTime=stop-1,limit=LIMIT))
        if exhausted or item.get('file') != name or item.get('url') != url:
            raise ValueError('Invalid pagination manifest')
        path = root/name
        digest = sha256(path)
        if digest != item['sha256'] or path.stat().st_size != item['bytes'] or path.stat().st_size > 1024**2:
            raise ValueError('Raw page integrity mismatch')
        before[str(path.resolve())] = digest
        rows = validate_page(json.loads(path.read_text()), symbol, cursor, stop)
        if item['records'] != len(rows):
            raise ValueError('Page count mismatch')
        records.extend(rows)
        exhausted = len(rows)<LIMIT or rows[-1]['funding_time_ms']==stop-1
        if rows:
            cursor=rows[-1]['funding_time_ms']+1
    if not exhausted or not records or m.get('api_pagination_exhausted') is not True:
        raise ValueError('Unfinished or empty funding history')
    normalized = root/'funding.json'
    digest = sha256(normalized)
    before[str(normalized.resolve())] = digest
    if digest != m['funding_sha256'] or json.loads(normalized.read_text()) != records:
        raise ValueError('Normalized funding differs from raw pages')
    gaps = sorted(set(b['funding_time_ms']-a['funding_time_ms'] for a,b in zip(records,records[1:])))
    derived = dict(records=len(records),first_funding_ms=records[0]['funding_time_ms'],
                   last_funding_ms=records[-1]['funding_time_ms'],observed_intervals_ms=gaps,
                   missing_mark_prices=sum(r['mark_price'] is None for r in records))
    if any(m.get(k)!=v for k,v in derived.items()):
        raise ValueError('Summary disagrees with saved events')
    if any(sha256(p)!=h for p,h in before.items()):
        raise ValueError('Input changed during audit')
    return dict(approved=False, integrity_passed=True, raw_conversion_equal=True,
                symbol=symbol,start=str(start),end_exclusive=str(end),**derived,
                reference_grid=grid_diagnostic(records,timestamp(start),stop),
                schedule_coverage_verified=False, inputs_sha256=before,
                runner_sha256=sha256(Path(__file__)),
                limitations=['Eight-hour grid is a diagnostic assumption, not verified historical contract rules.',
                             'Original millisecond timestamps are retained; no rounding for accounting.',
                             'A complete reference grid does not establish source completeness or executable P&L.'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--funding-dir',type=Path,required=True)
    p.add_argument('--symbol',default='ETHUSDT')
    p.add_argument('--start',type=date.fromisoformat,required=True)
    p.add_argument('--end',type=date.fromisoformat,required=True)
    p.add_argument('--reserve-from',type=date.fromisoformat,default=date(2026,9,1))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists() or a.output.is_symlink():
        p.error('Output exists; choose a new report path')
    r=audit(a.funding_dir,a.symbol,a.start,a.end,a.reserve_from)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
        f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))


if __name__=='__main__':
    main()
