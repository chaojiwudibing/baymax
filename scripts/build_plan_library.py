"""Build an attributed inventory; never invent missing creator prescriptions."""
import hashlib
import json
from pathlib import Path
from life_plan import validate_module
ROOT=Path(__file__).resolve().parents[1]

def action(id,title,instruction,time,minutes,metric,days=None,key=None):
    a=dict(id=id,title=title,instruction=instruction,time=time,minutes=minutes,metric=metric,action_key=key or id)
    if days: a['days']=days
    return a

def build():
    data=ROOT/'community/data'
    catalog=json.loads((data/'catalog.json').read_text());creators=json.loads((data/'creators.json').read_text())
    modules=[];inventory=[]
    paths={
      'food':('整理一份可用食谱','选择自己会做的一道菜，列出食材、已有库存和需要购买的材料；过敏食材先替换。食物克数和营养另交饮食核算，不从工具介绍推算。'),
      'nutrition':('试记一餐真实饮食','用工具的记录入口填写自己实际吃过的一餐，核对商品标签和生熟重量；没称重就标估算，不用数据库猜实际摄入。'),
      'training':('建立自己的活动记录','只记录自己已经会做且能安全完成的活动、感受和休息情况；不要直接照搬资料库动作或别人的重量次数。'),
      'outdoor':('回顾一次已有活动','整理一次已有步行或户外记录，确认定位数据的分享范围；不增加未知负荷，不公开家庭地址和路线起点。'),
      'body':('记录一个自己关心的习惯','只选择一个观察指标，填写真实情况；未记录留空，不用计划值补全。'),
      'mind':('查看一项自愿的放松练习','先阅读说明，选择自己舒适的内容；感到不适就停止。工具不能替代心理治疗，未体验的效果不填写。'),
      'sleep':('记录昨晚的实际作息','填写大致入睡和起床时间、醒后感受；未知留空，不把设备分期当医学诊断。'),
      'devices':('用合成数据检查接入方式','先阅读权限和导出说明，用合成数据理解输入输出；不授权全部健康记录或上传私有密钥。'),
      'care':('核对专业使用前提','阅读项目适用人群、专业资质和数据条件，列出需要专业人员确认的问题；不自行诊断、治疗或调整药物。')}
    for r in catalog['resources']:
        mid='tool-'+hashlib.sha256(r['id'].encode()).hexdigest()[:16]
        inventory.append(dict(source_id=r['id'],source_type='repository',title=r['name'],url=r['url'],module_id=mid if r['curated'] else None,status='structured-tool-workflow' if r['curated'] else 'needs-source-review',missing=[] if r['curated'] else ['相关性','原文阅读','许可','适用条件']))
        if not r['curated']: continue
        t,instruction=paths.get(r['category'],('检查用途','阅读原项目说明，确认与自己的目标相关。'))
        professional=r['category'] in ('care','devices')
        modules.append(dict(id=mid,title=r['name']+' · '+('资料评估' if professional else '使用计划'),author=r['repo'].split('/')[0],kind='tool',status='ready',category=r['category'],goal=r['description'],audience='开发者或专业人员；仅安排资料评估' if professional else '希望尝试该工具的成年人；须自行确认平台和安装条件',safety=r['note'],basis='Baymax 根据项目 README 编排的工具使用流程；不是原作者健康处方或疗效认证。时长和日期是可修改的编辑安排。',sources=[dict(title=r['repo'],url=r['url'],locator='README；快照 '+catalog['snapshotDate'])],license=r['license'],actions=[
          action('evaluate','了解 '+r['name'],'打开原始 README，确认平台、许可、维护情况和数据权限；不适用就移除本模块。','18:00',10,'适用 / 不适用及原因',[1],mid+':evaluate'),
          action('try',t,instruction,'18:00',15,'实际操作结果及困难',[2,3],mid+':try'),
          action('review','复盘 '+r['name']+' 的使用','比较自己的真实体验：是否容易坚持、数据能否导出、权限是否合适。选择继续、替换或停用；不要用 Star 数量判断健康效果。','18:00',10,'继续 / 替换 / 停用与原因',[7,14,21,30],mid+':review')]))
    for v in creators['videos']:
        mid='creator-'+v['id']
        inventory.append(dict(source_id=v['id'],source_type='creator',title=v['title'],url=v['url'],module_id=mid,status='needs-transcript-review',missing=['完整口述核对','数值与单位','适用条件','执行频率','调整和停止规则']))
        base=dict(author=v['creator'],category='creator',goal=v['description'],audience='对主题感兴趣的成年人；健康执行部分尚未核实',safety='章节不等于完整观点；不能据此安排负重、补剂剂量或热量处方。',sources=[dict(title=v['title'],url=v['url'],locator='平台章节，未核对完整口述；快照 '+creators['snapshotDate'])])
        modules.append(dict(base,id=mid,title=v['creator']+' · '+v['title'],kind='creator',status='draft',basis='仅定位来源，原作者可执行规划尚未获得；缺失项不得自动补齐。',actions=[action('verify','待核实作者执行建议','核对完整原文、适用人群、步骤、频次、数量单位及停止规则后，才可转为执行模块。','19:00',15,'审核结论',[1])]))
        chapters='；'.join(c['time']+' '+c['heading'] for c in v['chapters']) or '先取得原视频可核对的字幕或口述'
        modules.append(dict(base,id='read-'+v['id'],title='学习：'+v['title'],kind='learning',status='ready',basis='Baymax 原创学习安排，不是博主的健康执行计划；学习时间由编辑安排。',actions=[action('read','回看 '+v['creator']+' 的原视频','打开原视频并完整理解上下文。回看位置：'+chapters+'。逐条记下作者原话、时间点、适用条件和未说明项；观点、推广和本站补充说明分开。','19:00',20,'已核对的时间点和待确认问题',[1,8,15,22],'read:'+v['id'])]))
    official='https://www.who.int/news-room/fact-sheets/detail/physical-activity'
    common=dict(author='Baymax 编辑',kind='habit',status='ready',audience='一般成年人；可随时调整或不执行',safety='不适就停止；伤痛、疾病、妊娠等情况先确认适用性。不是临床或康复方案。',sources=[dict(title='WHO Physical activity',url=official,locator='Benefits / How much physical activity；2026-10-08 读取')],basis='编辑制定的低负担生活组织模板，WHO 仅提供活动与健康的背景依据；具体日程不是 WHO 或博主的处方。')
    modules.extend([
      dict(common,id='daily-reflection',title='每天留一点真实记录',category='body',goal='建立可复盘的30天记录，不追求完美打卡。',actions=[action('record','记录今天的感受','简记实际饮食、活动、睡眠与精力，以及最难坚持的一件事；没测量的数值留空。','21:00',5,'精力、困难、实际变化',key='daily-reflection')]),
      dict(common,id='gentle-movement',title='给轻松活动留个位置',category='training',goal='把自己适应的轻松活动放入日程。',actions=[action('move','一段舒适的轻松活动','在身体允许、环境安全时选择平常习惯的轻松活动，例如散步；10分钟只是日程预留，可缩短或取消，不代表达到了运动指南或需要忍痛坚持。','17:30',10,'实际时长和舒适程度',key='gentle-movement')]),
      dict(common,id='weekly-review',title='四次复盘，逐步调整',category='body',goal='依据真实记录调整，而不是根据一天的波动。',actions=[action('review','回顾这一阶段','打开真实记录，选一件能继续的事和一件需要减负的事；调整下阶段安排。第30天总结后再建立新周期，不自动无限加量。','21:15',15,'继续什么、改变什么、原因',[7,14,21,30],key='weekly-review')]),
      dict(common,id='meal-preparation',title='把吃饭安排得更从容',category='food',goal='盘点库存、安排采购并接入数据库核算的饮食方案。',actions=[action('prepare','准备本周的饮食安排','先盘点可用食材、过敏限制、厨具和预算；用 Baymax 饮食核算生成对应日期的完整菜单、克数、保存和采购清单。没有核算菜单前不把本提醒当作完整饮食计划。','11:00',15,'库存、限制和已核算菜单位置',[1,8,15,22],key='meal-preparation')])])
    reviewed=data/'reviewed-plans.json'
    if reviewed.exists():
        for addition in json.loads(reviewed.read_text())['modules']:
            validate_module(addition)
            modules=[m for m in modules if m['id']!=addition['id']]+[addition]
            for entry in inventory:
                if entry['module_id']==addition['id']:
                    entry['status']='source-reviewed' if addition['status']=='ready' else 'needs-source-review'
                    entry['missing']=[] if addition['status']=='ready' else entry['missing']
    for m in modules: validate_module(m)
    return dict(schema_version=1,snapshot_date='2026-10-08',modules=modules,inventory=inventory,
                counts={'sources':len(inventory),'structured_tools':sum(m['kind']=='tool' for m in modules),'creator_execution_ready':sum(m['kind']=='creator' and m['status']=='ready' for m in modules),'creator_pending':sum(m['kind']=='creator' and m['status']!='ready' for m in modules),'candidate_pending':catalog['candidateCount']})

if __name__=='__main__':
    result=build();(ROOT/'community/data/plans.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['counts'],ensure_ascii=False))
