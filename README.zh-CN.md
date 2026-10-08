# Baymax｜大白健康生活 Skill

[English](README.md) | **简体中文**

把健康社区与30天饮食管家合并为一个 skill：**来源整理 → 选择步骤 → 自由组合 → 完整30天 → 手机日历 → 真实记录与修订**。不绑定微软、Google或其他指定账号。

## 开始使用

将仓库安装为`baymax` skill，然后在Codex中说：

> 使用 $baymax，按我的目标，从社区选计划步骤，组合30天健康生活，接入我现有的手机日历。

```sh
git clone https://github.com/chaojiwudibing/baymax.git ~/.codex/skills/baymax
cd ~/.codex/skills/baymax
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python community/server.py
```

Windows PowerShell：

```powershell
git clone https://github.com/chaojiwudibing/baymax.git "$env:USERPROFILE\.codex\skills\baymax"
Set-Location "$env:USERPROFILE\.codex\skills\baymax"
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python community/server.py
```

已有目录先检查，不覆盖已有安装或私人数据。Python 3.10+；Excel使用openpyxl，Windows时区使用tzdata。Codex桌面可复用现有依赖环境。

打开 [本地社区](http://127.0.0.1:8848/)：在计划库选择整份模块或部分步骤，调整时间、星期、提醒，生成30天个人日程。可查看每一天、保存实际记录、修订并下载计划。浏览器会话隔离数据，但不是公开网站的账号系统。正式使用可用`--database /PRIVATE/.baymax/community.sqlite3`指定私有存储，备份数据库和导出的计划记录。

## 保留的饮食能力

USDA或有证据的商品标签 → SQLite → 逐餐核算 → 完整30天Excel。包含食材克数、生熟口径、营养、包装采购、备餐保存、替换、真实记录与Day 7/14/21/30复盘。未知营养不填0，不用计划值补实际摄入，修订通过`--journal`保留用户记录。

```sh
python scripts/calculate_plan.py --db /PRIVATE/nutrition.sqlite --plan /PRIVATE/meal-input.json --out /PRIVATE/new-version --strict
```

在“我的30天”选择核算结果`核算与来源.json`，日期与状态通过后合并餐食/采购/备餐/复盘提醒。日程模板不等于完整逐餐菜单。来源或执行审核有缺口时仍为草案。参阅 [数据协议](references/data-contract.md) 与 [饮食交付](references/plan-and-review.md)。生理结果不保证，核算通过不表示临床认证。

## 手机日历不绑账号

- **持续更新**：连接用户已有的CalDAV日历，如iCloud或用户已有/自托管的服务。连接后每次保存有效修订会自动更新未来事件，保留稳定UID，冲突时不覆盖手工备注。
- **免账号兜底**：ICS包含全部日程和提醒，可导入兼容手机日历。**文件导入不会自动同步后续修改**，重复导入可能重复。
- **订阅**：需另行授权HTTPS托管和接收端支持；刷新/通知因客户端而异。本版没有替用户部署订阅服务。

[15种设备组合与接入方法](references/calendar-sync.md) 覆盖Mac、Windows、iPhone、安卓及混合设备。安卓部分系统需要DAVx⁵等同步器或兼容ICS导入工具。仅有手机的用户可接收日历，生成/修改skill计划仍需有授权的运行环境。没有“所有品牌零安装零账号自动同步”的不实承诺。

```sh
python scripts/calendar_sync.py export --plan /PRIVATE/life-v1.json --out /PRIVATE/life-v1.ics
# 完成用户自己的账号连接和上传授权后：
python community/server.py --database /PRIVATE/community.sqlite3 --calendar-config /PRIVATE/caldav.json --calendar-state-dir /PRIVATE/calendar-state --allow-calendar-upload
```

私有配置与安全凭据设置见日历文档。旧Microsoft To Do投放桥保留为用户主动选择的可选通道，不是默认要求。

## 内容进度与当前边界

快照：2026-10-08。社区包含1,359个仓库来源，81份已读项目的工具使用流程，10份博主学习安排和4份编辑原创生活组织模板。

**仍有1,278个候选未完成来源审核，10个博主执行模块缺完整口述核对，不能声称所有内容都已变成专业健康处方。** 台账保留每个来源与缺口，未审核模块不能进入健康执行日程。已有[内容审核与导入流程](references/community-planning.md)，可把核实后的作者建议逐步补成独立步骤。第三方观点、编辑安排与额外证据分开，保留来源和许可。

网页、组合引擎、饮食合并、日历导出与CalDAV同步已实现并本地测试；真实云日历认证、Windows运行、iPhone/安卓锁屏通知和所有品牌组合仍需用户环境验收。该仓库不是已经公开部署的多人社区或手机App，不提供手机端后台监控。

## 隐私与验证

只监听127.0.0.1，个人资料、SQLite、计划、Excel、凭据和同步状态不发布到GitHub。日历首次上传需用户授权；不默认发送健康档案。来源库保留作者链接，软件许可不自动覆盖第三方素材。

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s community/tests -v
node community/tests/check_frontend.cjs
node community/tests/check_planner.cjs
node community/tests/check_browser.cjs
```

浏览器检查需要Playwright和Chrome，可设置`PLAYWRIGHT_PATH`和`CHROME_PATH`；脚本用隔离数据库，不改私人数据。测试证明的范围见[验收记录](references/verification.md)。入口是 [SKILL.md](SKILL.md)。最初的短入口和本地记录结构受 [learn-by-building](https://github.com/chaojiwudibing/learn-by-building) 启发。
