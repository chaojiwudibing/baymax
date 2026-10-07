# -*- coding: utf-8 -*-
"""Recompute complete 30-day plans from local source IDs; never trust supplied totals."""
import argparse
import csv
import json
import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from nutrition_db import KEYS, get_food, positive


def rollup(parts):
    return {k: {'value': round(sum(p[k] for p in parts), 6) if all(p[k] is not None for p in parts) else None,
                'known_subtotal': round(sum(p[k] for p in parts if p[k] is not None), 6),
                'missing_items': sum(p[k] is None for p in parts)} for k in KEYS}


def grams(item):
    q = positive(item['quantity'], 'quantity')
    if item['unit'] == 'g':
        return q
    if item['unit'] == 'kg':
        return q * 1000
    if item['unit'] == 'ml':
        if not item.get('conversion_evidence'):
            raise ValueError('ml conversion needs density evidence')
        return q * positive(item['density_g_ml'], 'density_g_ml')
    raise ValueError('unsupported unit; convert pieces/cooked weight with evidence first')


def calculate(plan, db):
    start = date.fromisoformat(plan['start_date'])
    if len(plan['days']) != 30:
        raise ValueError('exactly 30 days required')
    if not plan.get('foods'):
        raise ValueError('foods registry required')
    con = sqlite3.connect('file:' + str(Path(db).resolve()) + '?mode=ro', uri=True)
    registry, gaps = {}, set()
    try:
        for alias, spec in plan['foods'].items():
            food = get_food(con, spec['food_id'])
            if food['basis'] != 'per100g':
                raise ValueError('unsupported database basis')
            if spec.get('match') not in ('matched-general', 'exact-label', 'reference', 'unresolved'):
                raise ValueError('invalid food match status')
            if spec['match'] in ('reference', 'unresolved') or not spec.get('match_evidence'):
                gaps.add('食物未核实匹配：' + alias)
            if spec['match'] == 'exact-label' and food['source'].get('kind') == 'government-database':
                raise ValueError('general database cannot be an exact label')
            if not spec.get('weight_basis'):
                raise ValueError('missing weight_basis: ' + alias)
            positive(spec['edible_yield'], 'edible_yield')
            if spec['edible_yield'] > 1:
                raise ValueError('edible_yield exceeds 1')
            if not spec.get('yield_evidence') or spec.get('yield_status') != 'verified':
                gaps.add('采购损耗/可食率为假设：' + alias)
            registry[alias] = dict(spec=spec, food=food)
    finally:
        con.close()
    if plan.get('quantities_complete') is not True:
        gaps.add('调味料等全部入口食材未确认完整计量')
    if plan.get('execution_reviewed') is not True:
        gaps.add('备餐/保存/食物限制及设备条件尚未完成执行审核')
    days, line_rows, needs = [], [], {}
    for index, day in enumerate(plan['days']):
        expected = str(start + timedelta(days=index))
        if day['date'] != expected:
            raise ValueError('dates must be continuous and ordered: ' + expected)
        types = [m['type'] for m in day['meals']]
        if not all(types.count(k) == 1 for k in ('早餐', '午餐', '晚餐')):
            raise ValueError('each day requires one breakfast/lunch/dinner')
        meals, all_values, needs[expected] = [], [], {}
        consumed_costs = []
        for meal in day['meals']:
            if not meal.get('ingredients') or not meal.get('steps') or not meal.get('storage'):
                raise ValueError('meal requires ingredients, steps and storage')
            values, ingredients = [], []
            for item in meal['ingredients']:
                alias = item['food']
                entry = registry[alias]
                if item.get('weight_basis') != entry['spec']['weight_basis']:
                    raise ValueError('weight basis mismatch: ' + alias)
                amount = grams(item)
                v = {k: n * amount / 100 if n is not None else None for k, n in entry['food']['nutrients'].items()}
                for k in KEYS:
                    if v[k] is None:
                        gaps.add('营养缺失：' + alias + '/' + k)
                values.append(v); all_values.append(v)
                needs[expected][alias] = needs[expected].get(alias, 0) + amount
                offer = entry['spec']['offer']
                pack = positive(offer['pack_g'], 'pack_g')
                price = offer.get('pack_price')
                consumed_costs.append(amount / entry['spec']['edible_yield'] / pack * price if price is not None else None)
                detail = dict(food=alias, grams=amount, food_id=entry['food']['id'], weight_basis=item['weight_basis'], nutrients=v)
                ingredients.append(detail)
                line_rows.append(dict(date=expected, meal=meal['type'], dish=meal['name'], food=alias,
                                      grams=amount, weight_basis=item['weight_basis'], food_id=entry['food']['id'], **v))
            meals.append(dict(meal, ingredients=ingredients, nutrients=rollup(values)))
        days.append(dict(date=expected, meals=meals, nutrients=rollup(all_values),
                         estimated_consumed_cost=round(sum(consumed_costs), 2) if all(c is not None for c in consumed_costs) else None))
    # Packages and prices are separate from food composition; inventory carries forward.
    stock = {alias: 0 for alias in registry}
    batch_rows = []
    batch_ids = set()
    shopping, coverage, last_purchase = [], [], None
    for batch in plan['shopping']:
        begin, end, purchase = (date.fromisoformat(batch[k]) for k in ('start', 'end', 'purchase_date'))
        if begin > end or purchase > begin or (last_purchase and purchase <= last_purchase):
            raise ValueError('invalid shopping interval/order')
        last_purchase = purchase
        interval = [str(begin + timedelta(days=i)) for i in range((end-begin).days+1)]
        if any(d not in needs for d in interval):
            raise ValueError('shopping coverage outside plan')
        coverage.extend(interval)
        if not batch.get('prep'):
            raise ValueError('shopping batch needs preparation instructions')
        for portion in batch.get('batches', []):
            bid = portion['id']
            if bid in batch_ids:
                raise ValueError('duplicate preparation batch ID')
            batch_ids.add(bid)
            if portion['prepare'] != str(purchase) or portion['eat'] not in interval or portion['portions'] != 1:
                raise ValueError('invalid single-portion preparation date/count')
            linked = [m for d in plan['days'] if d['date'] == portion['eat'] for m in d['meals'] if m.get('batch_id') == bid]
            if len(linked) != 1:
                raise ValueError('preparation portion must link to exactly one meal')
            def amounts(items):
                totals = {}
                for item in items:
                    if item['weight_basis'] != registry[item['food']]['spec']['weight_basis']:
                        raise ValueError('preparation basis mismatch')
                    totals[item['food']] = totals.get(item['food'], 0) + grams(item)
                return totals
            expected_amounts, input_amounts = amounts(linked[0]['ingredients']), amounts(portion['inputs'])
            if expected_amounts.keys() != input_amounts.keys() or any(abs(v-input_amounts[k]) > 1e-6 for k,v in expected_amounts.items()):
                raise ValueError('preparation inputs do not match meal quantities')
            if not portion.get('thaw') or not portion.get('storage'):
                raise ValueError('preparation needs thaw/storage details')
            for alias, amount in input_amounts.items():
                batch_rows.append(dict(batch_id=bid, prepare=portion['prepare'], eat=portion['eat'],
                                       thaw=portion['thaw'], portions=1, food=alias, grams=amount,
                                       weight_basis=registry[alias]['spec']['weight_basis'], storage=portion['storage']))
        for alias, entry in registry.items():
            net = sum(needs[d].get(alias, 0) for d in interval)
            if not net:
                continue
            spec = entry['spec']; offer = spec['offer']
            pack = positive(offer['pack_g'], 'pack_g')
            price = offer.get('pack_price')
            if price is not None:
                positive(price, 'pack_price', True)
            if offer.get('status') not in ('verified', 'estimated', 'unknown'):
                raise ValueError('invalid offer status')
            if offer.get('status') != 'verified' or price is None or not all(offer.get(k) for k in ('evidence', 'checked', 'sku', 'channel', 'conditions')):
                gaps.add('采购实价/规格未核实：' + alias)
            if offer.get('checked'):
                date.fromisoformat(offer['checked'])
            gross = net / spec['edible_yield']
            before = stock[alias]
            required = max(0, gross-before)
            packs = math.ceil(max(0, required-1e-8) / pack)
            after = before + packs*pack-gross
            stock[alias] = after
            if after > 0 and not spec.get('inventory_storage'):
                raise ValueError('carryover inventory needs storage: ' + alias)
            shopping.append(dict(purchase_date=str(purchase), start=str(begin), end=str(end), food=alias,
                                 edible_use_g=net, edible_yield=spec['edible_yield'], gross_use_g=gross,
                                 stock_before_g=before, packages=packs, pack_g=pack,
                                 purchased_g=packs*pack, stock_after_g=round(after, 6),
                                 cost=round(packs*price, 2) if price is not None else None,
                                 price_status=offer['status'], channel=offer.get('channel'),
                                 sku=offer.get('sku'), checked=offer.get('checked'), evidence=offer.get('evidence'),
                                 conditions=offer.get('conditions'), storage=spec.get('inventory_storage')))
        if batch.get('delivery_status') != 'verified':
            gaps.add('运费/自取条件未核实：' + str(purchase))
        if batch.get('delivery_cost') is not None:
            positive(batch['delivery_cost'], 'delivery_cost', True)
    if coverage != [d['date'] for d in days]:
        raise ValueError('shopping coverage must cover every day exactly once in order')
    for d in plan['days']:
        for m in d['meals']:
            if m.get('batch_id') and m['batch_id'] not in batch_ids:
                raise ValueError('meal refers to missing preparation batch')
    costs = [r['cost'] for r in shopping] + [b.get('delivery_cost') for b in plan['shopping']]
    total = round(sum(costs), 2) if all(c is not None for c in costs) else None
    substitutions = plan.get('substitutions', [])
    for option in substitutions:
        for kind in ('original', 'replacement'):
            if not option.get(kind):
                raise ValueError('substitution needs original and replacement ingredients')
            for item in option[kind]:
                if item['food'] not in registry:
                    raise ValueError('substitution food must have a source entry')
                positive(item['grams'], 'substitution grams')
    return dict(schema_version=1, status='数据协议通过' if not gaps else '草案：数据缺口未解决',
                disclaimer='核算结果是食物成分估算；不保证人体效果，不代表临床或食品安全审核。',
                gaps=sorted(gaps), sources=registry, days=days, shopping=shopping,
                estimated_purchase_total=total, line_rows=line_rows, operational_plan=plan['shopping'],
                profile=plan.get('profile'), target=plan.get('target'), assumptions=plan.get('assumptions', []), batch_rows=batch_rows,
                substitutions=substitutions)


def write_csv(path, rows, fields):
    # Spreadsheet formula protection for any untrusted descriptive text.
    def safe(v):
        return "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for r in rows:
            writer.writerow({k: safe(v) for k, v in r.items()})


def deliver(result, out, journal=None):
    try:
        from export_excel import export_workbook
    except ImportError as exc:
        raise ValueError('Excel export requires openpyxl; use the bundled runtime or install requirements.txt in a local virtual environment') from exc
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('output directory must be new or empty; preserve earlier plans and logs')
    out.mkdir(parents=True, exist_ok=True)
    (out/'核算与来源.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    write_csv(out/'逐餐食材.csv', result['line_rows'], ['date','meal','dish','food','grams','weight_basis','food_id']+list(KEYS))
    daily = []
    for d in result['days']:
        row = {'date': d['date'], 'estimated_consumed_cost_CNY': d['estimated_consumed_cost']}
        for k, n in d['nutrients'].items():
            row[k] = n['value']; row[k+'_known'] = n['known_subtotal']; row[k+'_missing'] = n['missing_items']
        daily.append(row)
    write_csv(out/'每日营养.csv', daily, list(daily[0]))
    write_csv(out/'采购.csv', result['shopping'], list(result['shopping'][0]))
    if result['batch_rows']:
        write_csv(out/'分份备餐.csv', result['batch_rows'], list(result['batch_rows'][0]))
    write_csv(out/'真实每日记录.csv', [{'date':d['date']} for d in result['days']],
              ['date','morning_weight_kg','waist_cm','actual_meals','substitutions','actual_kcal','intake_complete','hunger','energy','sleep_hours','symptoms','actual_spend'])
    def fmt(n):
        return '未知（已知小计 %.1f）' % n['known_subtotal'] if n['value'] is None else '%.1f' % n['value']
    md = ['# Baymax｜30天饮食计划', result['status'], result['disclaimer'],
          '\n## 个人目标与实施假设', json.dumps(result['profile'], ensure_ascii=False),
          '起始营养目标（估算，按真实记录复盘）：'+json.dumps(result['target'], ensure_ascii=False),
          *result['assumptions'], '\n## 数据缺口', *['- '+g for g in result['gaps']],
          '\n营养单位：kcal；蛋白/碳水/脂肪/纤维g；钙/铁/钠mg。缺失不是0。']
    for d in result['days']:
        md += ['\n## '+d['date'], '每日估算：'+' / '.join(k+' '+fmt(n) for k,n in d['nutrients'].items()),
               '食材消耗成本估算：'+str(d['estimated_consumed_cost'])+' CNY（与采购包装实付分开）']
        for m in d['meals']:
            md += ['\n### '+m['type']+' '+m.get('time','')+'｜'+m['name'],
                   *['- %s %.1fg（%s；%s）' % (i['food'],i['grams'],i['weight_basis'],i['food_id']) for i in m['ingredients']],
                   '本餐估算：'+' / '.join(k+' '+fmt(n) for k,n in m['nutrients'].items()),
                   *m['steps'], '保存/取用：'+m['storage'], '备餐批次：'+m.get('batch','当天现做')]
    md += ['\n## 采购与备餐', '包装库存和每项价格状态见采购.csv；预计采购合计：'+str(result['estimated_purchase_total'])+' CNY（含已填写运费，未核实项目为估价）。']
    for batch in result['operational_plan']:
        md += ['\n### '+batch['purchase_date']+'｜'+batch['start']+'—'+batch['end']]
        for r in result['shopping']:
            if r['purchase_date'] == batch['purchase_date']:
                md.append('- %s：净用%.1fg；采购%d包×%.1fg；费用%s；%s；渠道%s；证据%s' % (r['food'],r['edible_use_g'],r['packages'],r['pack_g'],r['cost'],r['price_status'],r['channel'],r['evidence'] or '未核实'))
        for step in batch['prep']:
            md.append(step if isinstance(step,str) else '｜'.join(str(step.get(k,'')) for k in ('time','title','detail')))
    md += ['\n## 记录与长期调整', '每天填写真实每日记录.csv，留空表示未记录。Day 7/14/21复盘执行及感受，至少两周趋势后讨论小幅热量调整。Day 30依据真实记录制定未来8–12周计划；未提供记录不编造结果。',
           '\n## 来源', *['- '+alias+'：'+e['food']['description']+'；'+json.dumps(e['food']['source'], ensure_ascii=False) for alias,e in result['sources'].items()]]
    (out/'30天饮食计划.md').write_text('\n'.join(md)+'\n', encoding='utf-8')
    export_workbook(result, out/'Baymax-30天饮食计划.xlsx', journal)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for k in ('db','plan','out'):
        p.add_argument('--'+k, required=True)
    p.add_argument('--strict', action='store_true')
    p.add_argument('--journal', help='Preserve actual records from an existing Excel workbook or CSV')
    args = p.parse_args()
    try:
        plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
        result = calculate(plan, args.db)
        deliver(result, args.out, args.journal)
        print(json.dumps({'status':result['status'],'gaps':len(result['gaps']),'excel':str((Path(args.out)/'Baymax-30天饮食计划.xlsx').resolve())},ensure_ascii=False))
        return 1 if args.strict and result['gaps'] else 0
    except (ValueError, KeyError, TypeError, sqlite3.Error) as e:
        print('Validation failed: '+str(e))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
