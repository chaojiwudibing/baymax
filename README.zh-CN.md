# Baymax｜大白饮食管家 Skill

[English](README.md) | **简体中文**

对话式私人饮食管家，支持健康饮食、减脂、增肌和身体重组。参考 [learn-by-building](https://github.com/chaojiwudibing/learn-by-building) 的简短入口、状态流程、本地记录及校验脚本结构。只做饮食规划，不制定运动计划。

## 安装与使用

将本仓库克隆到 Codex 的技能目录，目录名使用 `baymax`，随后输入 `$baymax`。

```sh
git clone https://github.com/chaojiwudibing/baymax.git ~/.codex/skills/baymax
```

如果目录已存在，先检查已有内容，避免覆盖。Python 3.9 或以上即可运行核算脚本，无需第三方依赖或营养 API 订阅。

初次只采集六组简短信息，之后读取本机档案继续服务。输出完整30天 Markdown、逐餐食材/每日营养/采购/分份备餐/真实记录 CSV，以及来源和审计 JSON。按真实记录在第7、14、21、30天复盘。

## 数据库与准确性

使用本机 SQLite。支持导入 USDA 官方 SR28 原始归档与有证据的具体商品标签。数据库和私人档案不随仓库发布，使用时依据 [数据协议](references/data-contract.md) 获取和导入。

```sh
python3 scripts/nutrition_db.py import-sr28 --archive /path/to/sr28asc.zip --db .baymax/data/nutrition.sqlite --accessed YYYY-MM-DD
python3 scripts/nutrition_db.py search --db .baymax/data/nutrition.sqlite --query "Chicken, broilers"
python3 scripts/calculate_plan.py --db .baymax/data/nutrition.sqlite --plan .baymax/plan-input.json --out .baymax/plans/new-version --strict
```

访问日期填写真实获取日期。SR28 是历史美国食物成分数据，不等于中国实际商品标签或最新 FDC 数据。未接入有授权的中国食物成分表、深圳实时价格，也不承诺人体效果。

营养按条目和重量计算，保留来源ID、版本和文件哈希。未知营养不是0；生熟/干重口径不一致拒绝核算；ml 转克数需密度证据；购物核算包括可食率、包装进位及库存结转。

`--strict`遇到未匹配食物、未知营养、未核实报价或未完成执行审核，保存草案并返回退出码1；格式错误返回2。校验通过仍是食物成分估算，不等于实验室检测、临床审核或效果保证。食物和SKU的证据仍需人工核对。

## 隐私与验证

健康档案、真实记录和计划默认仅保存在用户本机 `.baymax/`，不上传、不写入公开仓库。skill不能自行感知身体变化或自动监测。

```sh
python3 -m unittest discover -s tests -v
```

23项测试覆盖来源、缺失值、重量口径、日期、价格、库存、备餐一致性、严格模式和真实记录。测试使用合成数据，不包含开发者的个人健康资料。

入口：[SKILL.md](SKILL.md)。保存与复盘：[本地记录](references/local-records.md)。完整交付：[计划与复盘](references/plan-and-review.md)。
