"""Compose source-attributed actions into a versioned, local 30-day life plan."""
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from reminder_bridge import private_json

ROOT = Path(__file__).resolve().parents[1]

def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('计划编号只能使用 1–80 位字母、数字、横线或下划线')
    return value

def text(value, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 and c != '\n' for c in value):
        raise ValueError('文字内容为空、过长或包含控制字符')
    return value.strip()

def local_time(day, clock, tz):
    if not isinstance(clock, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock):
        raise ValueError('时间必须是 HH:MM')
    naive = datetime.fromisoformat(str(day) + 'T' + clock)
    aware = naive.replace(tzinfo=tz)
    if aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != naive:
        raise ValueError('该时间落在夏令时跳过区间，请更换时间：' + str(naive))
    # Explicitly reject ambiguous clocks instead of silently selecting a fold.
    if aware.utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset():
        raise ValueError('该时间在夏令时回拨时重复，请更换时间：' + str(naive))
    return aware

def validate_module(m):
    identifier(m['id'])
    for key in ('title', 'author', 'goal', 'audience', 'safety', 'basis'):
        text(m[key])
    if m['status'] not in ('ready', 'draft') or m['kind'] not in ('habit', 'tool', 'learning', 'creator', 'nutrition', 'exercise'):
        raise ValueError('无效的计划类型或审核状态')
    if not isinstance(m.get('sources'), list) or not m['sources']:
        raise ValueError('每个模块都需要原始来源')
    for s in m['sources']:
        text(s['title']); text(s['locator']); text(s['url'])
        if not s['url'].startswith('https://'):
            raise ValueError('来源必须使用 HTTPS')
    if m['kind'] in ('creator', 'nutrition', 'exercise') and m['status'] == 'ready':
        review = m.get('review', {})
        for key in ('reviewer', 'reviewed_at', 'evidence', 'suitability', 'rights'):
            text(review.get(key))
        date.fromisoformat(review['reviewed_at'])
    actions = m.get('actions', [])
    if not isinstance(actions, list) or not 1 <= len(actions) <= 30:
        raise ValueError('每份计划需要 1–30 个步骤')
    seen = set()
    for a in actions:
        identifier(a['id'])
        if a['id'] in seen: raise ValueError('步骤编号重复')
        seen.add(a['id'])
        for key in ('title', 'instruction', 'metric', 'action_key'):
            text(a[key])
        if type(a['minutes']) is not int or not 1 <= a['minutes'] <= 240:
            raise ValueError('时长必须为 1–240 分钟')
        local_time(date(2030, 1, 1), a['time'], timezone.utc)
        for field, low, high in [('days', 1, 30), ('weekdays', 0, 6)]:
            if field in a and (not isinstance(a[field], list) or not a[field] or any(type(x) is not int or not low <= x <= high for x in a[field])):
                raise ValueError('安排天数或星期无效')
    return m

def library():
    return json.loads((ROOT/'community/data/plans.json').read_text(encoding='utf-8'))

def compile_plan(request, modules, previous=None):
    plan_id = identifier(request.get('id', ''))
    title = text(request.get('title', '我的30天健康生活计划'), 120)
    start = date.fromisoformat(request['start'])
    try: tz = ZoneInfo(request['timezone'])
    except (ZoneInfoNotFoundError, TypeError, KeyError): raise ValueError('请选择有效的 IANA 时区；Windows 请安装 tzdata') from None
    if previous and (previous['id'] != plan_id or previous['start'] != str(start)):
        raise ValueError('同一计划修订须保留编号和起始日期；新周期请创建新计划')
    if request.get('suitability_confirmed') is not True:
        raise ValueError('请先确认所选计划的适用条件，疾病、伤痛和过敏限制需先解决')
    selections = request.get('selections')
    if not isinstance(selections, list) or not 1 <= len(selections) <= 30:
        raise ValueError('请选择 1–30 份计划模块')
    lookup = {m['id']: m for m in modules}
    events, sources, conflicts, selected_ids = [], [], [], set()
    goals = set()
    for selection in selections:
        mid = selection['module']
        if mid in selected_ids: raise ValueError('不能重复选取同一个模块')
        selected_ids.add(mid)
        if mid not in lookup: raise ValueError('计划模块不存在')
        m = validate_module(lookup[mid])
        if m['status'] != 'ready': raise ValueError('该来源仍待核实，不能直接用于健康执行：' + m['title'])
        sources.append(dict(id=mid, title=m['title'], author=m['author'], basis=m['basis'], sources=m['sources']))
        if m.get('exclusive_goal'): goals.add(m['exclusive_goal'])
        choices = selection.get('actions', [a['id'] for a in m['actions']])
        if not isinstance(choices, list) or not choices or len(set(choices)) != len(choices) or set(choices) - {a['id'] for a in m['actions']}:
            raise ValueError('请选择有效且不重复的步骤')
        overrides = selection.get('overrides', {})
        if not isinstance(overrides, dict) or set(overrides) - set(choices): raise ValueError('步骤自定义设置无效')
        for a in m['actions']:
            if a['id'] not in choices: continue
            o = overrides.get(a['id'], {})
            clock = o.get('time', a['time'])
            weekdays = o.get('weekdays', a.get('weekdays', list(range(7))))
            if not isinstance(weekdays, list) or not weekdays or any(type(x) is not int or x not in range(7) for x in weekdays):
                raise ValueError('每周至少选择一天')
            lead = o.get('reminder_minutes', 10)
            if type(lead) is not int or not 0 <= lead <= 1440: raise ValueError('提前提醒须在 0–1440 分钟之间')
            for n in range(1, 31):
                day = start + timedelta(days=n-1)
                if n not in a.get('days', list(range(1,31))) or day.weekday() not in weekdays: continue
                at = local_time(day, clock, tz)
                key = hashlib.sha256(f'{plan_id}|{mid}|{a["id"]}|{day}'.encode()).hexdigest()[:32]
                body = f'{a["instruction"]}\n\n记录：{a["metric"]}\n适用：{m["audience"]}\n注意：{m["safety"]}\n整理依据：{m["basis"]}\n来源作者：{m["author"]}'
                body += ''.join('\n'+s['title']+' · '+s['locator']+'\n'+s['url'] for s in m['sources'])
                events.append(dict(id=key, at=at.isoformat(), title=a['title'], body=body,
                                   minutes=a['minutes'], reminder_minutes=lead, module=mid, action=a['id'], action_key=a['action_key'], kind=m['kind']))
    if len(goals) > 1: conflicts.append('所选模块有互斥目标：' + '、'.join(sorted(goals)))
    # Nutrition remains the existing auditable computation, not model-invented menu numbers.
    audit = request.get('nutrition_audit')
    nutrition_status = '未加入逐餐饮食方案'
    if audit is not None:
        from export_reminders import export
        if not isinstance(audit, dict) or len(audit.get('days', [])) != 30:
            raise ValueError('饮食核算文件必须覆盖完整30天')
        if [d['date'] for d in audit['days']] != [str(start+timedelta(days=i)) for i in range(30)]:
            raise ValueError('饮食与生活计划的30天日期必须一致')
        if audit.get('gaps') or audit.get('status') != '数据协议通过':
            raise ValueError('饮食仍有核算缺口，请先在饮食 skill 中解决后再合并执行')
        diet = export(audit, plan_id, '+00:00')
        for e in diet['events']:
            dt = datetime.fromisoformat(e['at']); e['at'] = local_time(dt.date(), dt.strftime('%H:%M'), tz).isoformat()
            e.update(minutes=10, reminder_minutes=0, module='nutrition-audit', action_key='nutrition:'+e['kind'])
        events.extend(diet['events'])
        nutrition_status = '已合并核算通过的30天逐餐、采购、备餐与复盘安排（成分估算）'
    events.sort(key=lambda e: (e['at'], e['id']))
    if not events: raise ValueError('当前日期与星期设置没有产生任何步骤')
    for i, e in enumerate(events):
        t = datetime.fromisoformat(e['at']); end = t+timedelta(minutes=e['minutes'])
        for other in events[i+1:]:
            ot = datetime.fromisoformat(other['at'])
            if ot.date() != t.date(): break
            if other['action_key'] == e['action_key']:
                conflicts.append(f'{t.date()} 重复目标：{e["title"]} / {other["title"]}')
            elif ot < end:
                conflicts.append(f'{t.date()} 时间重叠：{e["title"]} / {other["title"]}；请调整时间')
    revision = previous['revision'] + 1 if previous else 1
    return dict(schema_version=1, id=plan_id, plan_id=plan_id, title=title, start=str(start), timezone=request['timezone'],
                revision=revision, updated_at=datetime.now(timezone.utc).isoformat(),
                status='conflicts' if conflicts else 'ready', conflicts=list(dict.fromkeys(conflicts)), nutrition_status=nutrition_status,
                selections=selections, sources=sources, events=events,
                days=[dict(day=i+1, date=str(start+timedelta(days=i)), events=[e['id'] for e in events if e['at'][:10]==str(start+timedelta(days=i))]) for i in range(30)])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', required=True); p.add_argument('--out', required=True)
    p.add_argument('--library'); p.add_argument('--previous')
    a=p.parse_args()
    modules=json.loads(Path(a.library).read_text())['modules'] if a.library else library()['modules']
    req=json.loads(Path(a.request).read_text())
    old=json.loads(Path(a.previous).read_text()) if a.previous else None
    result=compile_plan(req, modules, old); private_json(a.out, result, replace=False)
    print(json.dumps({'revision':result['revision'],'events':len(result['events']),'status':result['status']},ensure_ascii=False))
    return 1 if result['conflicts'] else 0

if __name__=='__main__': raise SystemExit(main())
