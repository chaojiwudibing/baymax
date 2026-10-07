#!/usr/bin/env python3
"""Export only meal/task details from a calculated audit; never export the profile."""
import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from reminder_bridge import instant, load_plan, private_json


def export(audit, plan_id, offset='+08:00'):
    if len(audit['days']) != 30 or not plan_id.strip():
        raise ValueError('A complete 30-day audit and stable plan ID are required')
    instant('2000-01-01T00:00:00' + offset)
    events = []
    def add(day, clock, kind, title, body):
        at = day + 'T' + clock + ':00' + offset
        instant(at)
        key = hashlib.sha256((plan_id + '|' + day + '|' + kind).encode()).hexdigest()[:32]
        events.append(dict(id=key, at=at, title=title, body=body, kind=kind))
    for idx, d in enumerate(audit['days']):
        if sorted(m['type'] for m in d['meals']) != sorted(('早餐', '午餐', '晚餐')):
            raise ValueError('Expected one breakfast, lunch and dinner per day')
        for m in d['meals']:
            alarm = datetime.fromisoformat(d['date'] + 'T' + m['time'] + ':00' + offset) - timedelta(minutes=15 if m['type'] == '早餐' else 30)
            body = '计划用餐时间：' + m['time'] + '\n\n食材（按计划重量口径）：\n'
            body += '\n'.join('%s %g克（%s）' % (i['food'], i['grams'], i.get('weight_basis', '见Excel')) for i in m['ingredients'])
            body += '\n\n做法：\n' + '\n'.join('%d. %s' % (j + 1, step) for j, step in enumerate(m['steps']))
            body += '\n\n' + m.get('storage', '当天现做。') + '\n\n营养属于数据库成分估算；实际食材仍需核对标签。已知过敏食材先避开并反馈替换。'
            add(alarm.date().isoformat(), alarm.strftime('%H:%M'), m['type'], d['date'] + ' ' + m['type'] + '｜' + m['name'], body)
        body = '我的记录\n今天晨重（没测留空）：\n实际三餐及替换：\n饥饿与精力：\n备注：\n\n勾选完成不代表实际摄入；记录不会自动回传给大白。'
        if idx + 1 < len(audit['days']):
            body += '\n\n次日准备：只将次日冷冻份移入≤4°C冰箱解冻，米饭当餐现煮。'
        add(d['date'], '21:30', 'record', d['date'] + '｜记录饮食与感受', body)
    for idx, op in enumerate(audit.get('operational_plan', [])):
        day = op['purchase_date']
        items = [r for r in audit['shopping'] if r['purchase_date'] == day and r['packages'] > 0]
        body = '覆盖' + op['start'] + '至' + op['end'] + '；先盘点实际可用库存。\n\n'
        body += '\n'.join('□ %s：%g克（%g份×%g克），预算¥%.2f\n建议渠道：%s' %
            (r['food'], r['purchased_g'], r['packages'], r['pack_g'], r['cost'], r['channel']) for r in items)
        body += '\n\n预算不是核实后的门店报价。实价、库存、包装与运费按购买时更新；肉鱼乳品保冷运输，及时入冰箱。'
        shopping_day, shopping_time = day, '10:00'
        if idx == 0:
            shopping_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat(); shopping_time = '20:00'
            body = '启动采购：先确认明早食材可用或能及时送达。若本时段已过，需明确另行采购安排，不假定已有库存。\n\n' + body
        add(shopping_day, shopping_time, 'shopping', day + ' 采购｜食材清单', body)
        body = '\n\n'.join(s['time'] + ' · ' + s['title'] + '\n' + s['detail'].replace('分份备餐.csv', 'Excel「分装标签」').replace('CSV', 'Excel「分装标签」') for s in op['prep'])
        body += '\n\n按餐分装：\n' + '\n\n'.join(b['eat'] + ' ' + b['id'].split('-')[-1] + '\n' +
            '；'.join('%s %g克' % (i['food'], i['quantity']) for i in b['inputs']) for b in op.get('batches', []))
        add(day, '14:00', 'prep', day + ' 备餐｜称量分装与保存', body)
    for idx in (6, 13, 20, len(audit['days']) - 1):
        day = audit['days'][idx]['date']
        add(day, '21:45', 'review', day + '｜饮食复盘', '依据实际饮食、体重趋势、饥饿和精力调整饮食。把真实记录告诉大白或填写Excel后复盘；完成勾选不代表实际摄入。体脂需要实测，不能从体重推算。')
    return dict(schema_version=1, plan_id=plan_id, clock_policy='fixed UTC offset; regenerate when local offset changes',
                events=sorted(events, key=lambda e: instant(e['at'])))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit', required=True); p.add_argument('--out', required=True)
    p.add_argument('--plan-id', required=True, help='Keep stable when revising the same period')
    p.add_argument('--utc-offset', default='+08:00')
    args = p.parse_args()
    audit = json.loads(Path(args.audit).read_text(encoding='utf-8'))
    if len(audit['days']) != 30: raise ValueError('Expected a complete 30-day audit')
    private_json(args.out, export(audit, args.plan_id, args.utc_offset), replace=False)
    load_plan(args.out)
    print('Private manifest saved. No tasks uploaded; no health profile included.')


if __name__ == '__main__':
    main()
