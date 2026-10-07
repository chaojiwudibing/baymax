# -*- coding: utf-8 -*-
"""Read actual Excel/CSV records, report observed windows without invented values."""
import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path
from nutrition_db import positive

def review(path, start):
    start = date.fromisoformat(start)
    if Path(path).suffix.lower() == '.xlsx':
        from export_excel import read_records
        rows = read_records(path)
    else:
        with Path(path).open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.DictReader(f))
    seen, weights, complete = set(), {}, []
    for r in rows:
        d = date.fromisoformat(r['date'])
        if d in seen:
            raise ValueError('duplicate journal date')
        seen.add(d)
        if not start <= d < start+timedelta(days=30):
            raise ValueError('journal date outside 30-day period')
        if d > date.today():
            if any(v.strip() for k,v in r.items() if k != 'date' and v):
                raise ValueError('future dated observations are not actual records')
            continue
        if r.get('morning_weight_kg','').strip():
            weights[d] = positive(float(r['morning_weight_kg']), 'weight')
        if r.get('intake_complete','').lower() == 'true' and r.get('actual_kcal','').strip():
            kcal = positive(float(r['actual_kcal']), 'actual_kcal', True)
            complete.append(kcal)
    windows = []
    for offset in (0,23):
        vals = [v for d,v in weights.items() if start+timedelta(days=offset) <= d < start+timedelta(days=offset+7)]
        windows.append({'sample_count':len(vals),'mean_kg':round(sum(vals)/len(vals),3) if vals else None})
    sufficient = all(w['sample_count']>=3 for w in windows)
    return {'start_date':str(start),'baseline_first7':windows[0],'end_last7':windows[1],
            'observed_weight_change_kg':round(windows[1]['mean_kg']-windows[0]['mean_kg'],3) if sufficient else None,
            'complete_intake_days':len(complete), 'mean_reported_complete_intake_kcal':round(sum(complete)/len(complete),1) if complete else None,
            'status':'可作阶段描述，需结合实际执行与感受' if sufficient else '记录不足，仅暂定复盘',
            'note':'体重差不是脂肪变化；未自动估计能耗、体脂或调整热量。'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--journal',required=True); p.add_argument('--start',required=True); p.add_argument('--out',required=True)
    a=p.parse_args()
    out=Path(a.out)
    if out.exists():
        raise ValueError('refuse overwriting earlier review')
    result=review(a.journal,a.start)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(result['status'])
if __name__=='__main__':
    main()
