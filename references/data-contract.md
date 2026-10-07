# 数据协议与可复核计算

## 准确性有三个层次

1. **来源真实**：数据库/标签确实存在，保存来源条目、版本、URL或本机证据文件、获取日期、许可、原始文件哈希。哈希保证文件可辨识，不能单独证明下载来源或实验室测定。
2. **匹配适用**：部位、品种、生熟、带皮/骨、脂肪含量、强化成分、品牌SKU与实际食物相符。关键词搜索或模型说“差不多”不算匹配。基础食材成分也有自然波动；匹配通过依然是估算。
3. **核算正确**：统一可食部重量，按每100g比例求和；未知值不当零。对人体能量消耗和效果只能通过真实记录持续校正。

官方入口：USDA FDC https://fdc.nal.usda.gov/；SR28原始归档 https://www.ars.usda.gov/ARSUserFiles/80400525/Data/SR/SR28/dnload/sr28asc.zip 。SR28是历史资料，不把它称作最新FDC数据库。真实访问后记录访问日期；保留压缩包，不在导入时解压执行文件。中国食物成分表须核实授权，未取得就不能声称已接入。Open Food Facts的ODbL等许可需单独处理；本skill不默认打包其数据。

脚本来源ID包含SHA256和NDB编号，重复导入同一归档不会复制条目。商品标签每次使用新版本ID，禁止覆盖既有证据。标签导入是记录用户/厂商提供的证据，不是自动认证。联网查询只传商品/食物关键词，不能上传健康档案。

## 计划JSON v1

必填：`start_date`, `foods`, `days`（连续30个日期）, `shopping`（无重叠完整覆盖30天）。个人信息在 `profile`，估算目标在 `target`，假设在 `assumptions`。`quantities_complete`（全部入口食材含调料已计量）、`execution_reviewed`（安全限制/保存/设备人工审核）未经确认必须false。

`foods`以计划食材名为键，每项：

```json
{
  "food_id": "从数据库search返回的完整ID",
  "match": "reference",
  "match_evidence": "",
  "weight_basis": "可食部生重",
  "edible_yield": 1,
  "yield_status": "assumed",
  "yield_evidence": "",
  "inventory_storage": "按实际商品标签和使用日期安排冷藏/冷冻，不能自动延长保质期",
  "offer": {
    "pack_g": 500, "pack_price": null, "status": "unknown",
    "channel": "待核实", "sku": "", "evidence": "", "checked": null,
    "conditions": "运费、起送、会员条件待核实"
  }
}
```

- `match`：`reference`/`unresolved`无法严格通过；`matched-general`是有证据的同种基础食材估算；`exact-label`是实际相同SKU标签。不能为通过校验而改变状态。匹配证据描述部位/生熟/脂肪及SKU核对过程，读过证据再填写。
- `weight_basis`写清可食生重、干重、净重或具体熟重。输入条目必须同口径。把熟重转换到生重时先记录该次实测产率，并转换回源口径；不能用通用倍数悄悄折算。
- `edible_yield`是采购总重到可食重量的比率(0,1]。包装进位先扣有效库存，再按毛重需求进位。净肉可以是1但仍须说明采购规格；含皮/骨有实测或来源时才设verified。
- 采购报价含SKU、克数、每包价格、日期、渠道、证据和条件。估价填estimated，缺价填unknown/null。库存只能结转在安全保存和保质期内的实际可用量；脚本仅算重量，执行审核须逐项确认。

`days`每项：

```json
{"date":"2026-10-08","meals":[
  {"type":"早餐","time":"09:30","name":"菜名",
   "ingredients":[{"food":"食材键","quantity":100,"unit":"g","weight_basis":"可食部生重"}],
   "steps":["具体做法"],"storage":"保存和食用安排","batch":"批次ID"}
]}
```

每天必须有且仅有一个早餐、午餐、晚餐，可加加餐。上面只是结构示例，不能作为30天交付。quantity必须为有限正数；g/kg支持。ml必须附`density_g_ml`与`conversion_evidence`，不能默认ml=g。份/个需先实测可食重量换成g；不伪造克数。脚本始终忽略手填营养值，由数据库重算。

`shopping`每项：`purchase_date`, `start`, `end`, `prep`（完整时间步骤或对象列表）, `delivery_cost`（无价null）, `delivery_status`。第一批允许开计划前/当天启动采购；其后对齐周末。脚本核对完整日期覆盖，周末、冷链、分装解冻、批次产量和厨房容量由智能体依完整交付规范审核，不能把重量算对当作食品安全通过。

## 标签JSON

导入文件为数组，条目包含 `id`（新的版本ID）, `description`, `brand`, `sku`, `evidence`（真实标签图片/官方页，本地文件可保存哈希）, `accessed`, `license`（如私人本地使用，商业再分发未授权）, `basis: per100g`, `nutrients`。

营养键：`kcal`, `protein`, `carbs`, `fat`, `fiber`, `calcium`, `iron`, `sodium`；宏量单位g，微量mg。未标的不填或null。能量若标签kJ，除以4.184转kcal并在证据注明；per100ml先有实测/可靠密度再转per100g，注明原值和转换。不用宏量4/4/9替代来源能量；4/4/9只做异常检查。

## 验收与输出

`--strict`有缺口返回1，格式/单位错误返回2；正常草案返回0，须看结果status。缺失营养总计null，并提供已知小计和缺失食材数量。缺价格总成本null。价格估算可计算总额但仍阻止严格通过。所有验证都是协议检查，无法自动判定证据是否伪造/商品是否真的匹配，发布前必须读证据人工核对。

输出新目录，拒绝覆盖旧版和真实记录。CSV防护公式注入。来源证据完整保存于核算JSON。计划支持真实标签而当前本机数据库只是USDA SR28；不可把“支持接入”写成“已经接入中国数据库/深圳实时价格”。

逐份备餐使用 `shopping[].batches`：每份有唯一 `id`、`prepare`、`eat`、`thaw`、`portions:1`、`storage`、`inputs`（与餐食ingredients同结构）。关联餐的 `batch_id` 等于id。脚本核对日期、重复ID、单份数量和投入食材是否与餐一致，输出分份备餐CSV。早餐现做可没有batch_id；全量计划的午晚餐须有明确现做或备餐安排，人工核对没有漏项。多份锅菜先拆成可核对的单份，不虚构熟重产率。
