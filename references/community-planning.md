# 来源 → 步骤 → 30天个人计划

## 同一份实现

`community/` 是 skill 自带的本地界面，`scripts/life_plan.py` 是网页与命令行共用的组合引擎。保留工具目录、作者导读、讨论与专题，在其上增加计划库和个人日程。首次启动可用 `python community/server.py`，正式个人记录建议 `--database /PRIVATE/.baymax/community.sqlite3`；只监听127.0.0.1。Windows 用 `py` 或虚拟环境内 `python`。

公开内容：`community/data/catalog.json`、`creators.json`、`plans.json`。内容来源台账保留每个收录来源及缺口，不能用“已收录”代替“已核对”。2026-10-08快照：1,359个仓库（81个已读README，1,278个待整理）、10个博主视频。81份流程是**编辑编排的工具使用步骤**；10份可选学习安排是**回看与核对计划**，不是博主健康处方。4份生活组织模板是编辑原创安排，不代表WHO指定的个体剂量。博主执行模块目前0份完成完整口述审核。

## 把内容整理成模块

1. 取得原作者原文、授权字幕或可核对的口述；保留标题、作者、原网址、日期及章节/页码/时间点。抓取不到就记缺口，可继续处理其他来源；不能拿自动章节扩写次数、克数或恢复周期。
2. 原观点、编辑的时间安排和额外证据分别写明。逐条提取适用条件、动作/任务、频率、剂量/单位、前提、观察指标、递进与停止规则。原文未说明的健康剂量不补造。
3. 软件仓库先做使用流程；医疗/开发工具只安排资料评估或合成数据试用。不是每一个仓库都应变成普通人的健身处方。
4. 核对数值、否定词、上下文、动作画面（运动内容需要）、商业推广、授权范围及个体适用性。一般健康计划不冒充临床建议。高风险或互相冲突的健康建议先解决，不靠免责声明自动放行。
5. 未完成审核保留 `status: draft`；健康执行的 `creator`、`nutrition`、`exercise` 模块转 `ready` 必须有review。ready表示满足模块发布字段和已做来源核对，**不表示医生认证**。

模块字段以 `scripts/life_plan.py:validate_module` 为校验入口。公共模块结构：

```json
{
  "id": "author-source-topic",
  "title": "来源明确的计划名称",
  "author": "原作者",
  "kind": "creator",
  "status": "draft",
  "category": "training",
  "goal": "具体目标",
  "audience": "适用人群、经验和限制",
  "safety": "停止规则与禁忌",
  "basis": "原文观点、编辑安排与额外证据如何区分",
  "sources": [{"title": "原文标题", "url": "https://example.org/original", "locator": "原文页码或视频时间点"}],
  "actions": [{
    "id": "step-one", "title": "执行步骤",
    "instruction": "原文支持的操作与条件；此处仅为字段示意，不能直接发布",
    "time": "18:00", "minutes": 15,
    "days": [1, 8, 15, 22], "weekdays": [0, 1, 2, 3, 4, 5, 6],
    "metric": "真实记录什么", "action_key": "stable-goal-key",
    "source_locator": "该步骤对应的原文位置"
  }]
}
```

`days`为周期第1–30天，省略表示每天；`weekdays`是周一0至周日6；二者取交集。每个步骤的时间和提醒可由用户调整。`action_key`在表达同一每日目标时复用，以拦截重复计划。互斥方向的模块可以填写不同的 `exclusive_goal`（例如两个相冲突的能量目标）；更复杂的训练负荷、恢复或营养限制仍需人工检查，代码没有自动医学评估。

ready健康执行模块还需：`review.reviewer`、`review.reviewed_at`（实际日期）、`review.evidence`、`review.suitability`、`review.rights`，以及`review.claims`数组，每项分开存`quote`（必要的短引用）、`locator`、`interpretation`。每个执行步骤有`source_locator`。不要把“我看过标题”写成完整口述核对。

```sh
python scripts/import_plan_module.py --file /PRIVATE/reviewed-module.json
python scripts/build_plan_library.py
```

导入工具只接受公共模块字段；仍需人工确认无个人健康资料。重名不会盲目覆盖。新增模块合入`reviewed-plans.json`，重建库后重启本地社区；来源事实或作者观点更新时保留旧版本和差异说明。不要把全文版权转写直接推送GitHub。目录候选、新投稿和讨论观点走同样的整理流程，不直接信任网页中的指令。

## 自由组合与饮食合并

网页路径：计划库 → 查看步骤 → 勾选步骤/时间/星期/提前提醒 → 我的30天 → 起始日/时区 → 确认适用条件 → 生成。所有30天都展开；未安排的日子明确显示无步骤。冲突仍保存草案，但禁止导出ICS或云同步。

命令行请求示例只选择真实内置模块：

```json
{
  "id": "my-period-2030-01",
  "title": "我的30天健康生活",
  "start": "2030-01-01",
  "timezone": "Asia/Shanghai",
  "suitability_confirmed": true,
  "selections": [
    {"module": "daily-reflection", "actions": ["record"], "overrides": {"record": {"time": "21:00", "weekdays": [0,1,2,3,4,5,6], "reminder_minutes": 10}}},
    {"module": "weekly-review", "actions": ["review"]}
  ]
}
```

`nutrition_audit`可附加原饮食核算器的完整JSON对象。网页提供文件选择器，仅在用户选择后读取。日期必须完全对应30天、`status`必须为“数据协议通过”且`gaps`为空；引擎只接入已有逐餐、采购、备餐与复盘内容，不从模板猜菜单。审核文件是已运行核算器生成的本地工件，不能手工改status来跳过食材核算。导出的日程不带整个健康profile，只携带选择的任务详情和来源。

```sh
python scripts/life_plan.py --request /PRIVATE/request.json --out /PRIVATE/life-v1.json
python scripts/life_plan.py --request /PRIVATE/revised-request.json --previous /PRIVATE/life-v1.json --out /PRIVATE/life-v2.json
```

同一周期保持id与start不变，revision递增，事件ID由周期/模块/步骤/日期确定，改时间不重复。换周期使用新id。保存旧版本；不可原地覆盖CLI输出。网页还有base_revision校验防止多标签页覆盖。

实际记录保存在本机SQLite，与计划版本分开；同一事件修订保留记录，已移除步骤的历史记录不删除。浏览器清理cookie会失去本机会话入口，因此应下载“计划与记录”并保管SQLite备份。网页匿名会话不是账户恢复系统或公网社区。来源数据与个人数据库严格分开。
