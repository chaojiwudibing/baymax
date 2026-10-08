"""Import a source-reviewed public plan module; never accepts private health profiles."""
import argparse
import json
from pathlib import Path
from life_plan import validate_module
from reminder_bridge import private_json
from build_plan_library import build, ROOT

ALLOWED={'id','title','author','goal','audience','safety','basis','status','kind','sources','actions','category','license','review','exclusive_goal'}
def import_module(module, destination):
    if not isinstance(module,dict) or set(module)-ALLOWED:
        raise ValueError('只允许公共计划字段，禁止夹带用户档案或其他未知字段')
    validate_module(module)
    if module['status']=='ready' and module['kind'] in ('creator','exercise','nutrition'):
        if not module['review'].get('claims') or not isinstance(module['review']['claims'],list):raise ValueError('缺少逐条原话与定位证据')
        for claim in module['review']['claims']:
            if not all(isinstance(claim.get(k),str) and claim[k].strip() for k in ('quote','locator','interpretation')):raise ValueError('原话、定位与整理解释必须分开')
        for a in module['actions']:
            if not a.get('source_locator'):raise ValueError('每个执行步骤都必须对应原文位置，不能从标题补齐')
    dest=Path(destination);previous=json.loads(dest.read_text()) if dest.exists() else {'modules':[]}
    if any(m['id']==module['id'] for m in previous['modules']):raise ValueError('模块已存在；先检查现有版本，不能盲目覆盖')
    previous['modules'].append(module);private_json(dest,previous)
    return module['id']

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--file',required=True);p.add_argument('--destination',default=str(ROOT/'community/data/reviewed-plans.json'));a=p.parse_args()
    module=json.loads(Path(a.file).read_text());print(import_module(module,a.destination))
    if Path(a.destination).resolve()==(ROOT/'community/data/reviewed-plans.json').resolve():
        (ROOT/'community/data/plans.json').write_text(json.dumps(build(),ensure_ascii=False,indent=2),encoding='utf-8')
        print('公共计划库已更新；重启本地社区以读取新版本。来源核对不等于临床认证。')

if __name__=='__main__':main()
