# 到时投放：Windows、Android、iPhone

这是可选的跨平台执行通道，Excel仍是完整计划与真实记录的默认交付。接收端采用微软To Do；使用同一个个人微软账号登录Windows、Android、iPhone或网页版。到时才创建当前任务，未来任务留在私有计划文件里。完成的可在客户端隐藏；漏做的保留。不是“完成勾选触发下一条”。

**现状**：模块通过本地模拟接口验证，尚未声称真实微软账号、云端部署或手机通知验收通过。中国由世纪互联运营的Graph服务不受此API支持。本实现用`consumers`登录端点，面向个人微软账号，尚未支持企业租户配置。

## 从已核算计划生成私有投放文件

```sh
python scripts/export_reminders.py --audit /private/核算与来源.json --out /private/reminders.json --plan-id my-period --utc-offset +08:00
python scripts/reminder_bridge.py preview --manifest /private/reminders.json
```

投放文件只有餐食、克数、做法、采购备餐及记录/复盘提示，不包含用户档案、年龄、现有体重或体脂目标。同一周期修订保持`plan-id`不变；已投放任务不自动覆盖用户备注。时间使用明确UTC偏移；更换时区或夏令时变化时重新生成，不能把固定偏移当成全球时区规则。启动采购默认前一天20:00：若已错过，单独解决采购，不能假定用户已有库存。

## 真实启用前需要的连接

先解释并取得用户对**餐食/采购任务详情上传到其微软账号和选定云主机**的授权，再执行连接及投放。不得把“本地安装skill”当作允许上传健康信息。令牌权限为微软任务读取/写入，授权范围不只限于一个清单；程序只在选定清单里核对任务。禁止把令牌、私有计划、记录或数据库推到公开GitHub。

1. 在Microsoft Entra注册支持个人微软账号的公共客户端应用，启用设备代码流/公共客户端登录，配置委派`Tasks.ReadWrite`，请求`offline_access`。取得应用client ID。
2. 用户在可信的个人环境执行下面的`connect`，亲自在微软页面登录和审核权限；脚本不收集账号密码。令牌只保存到指定私有文件并自动刷新，失效或撤销后需要重连。
3. 新建专用To Do清单，保存返回的list ID。用户在手机登录同一账号，并允许To Do通知与后台同步。
4. 把私有投放文件、令牌和持久状态放进用户选定的云端私有存储，在云端持续运行单个worker。Mac/Windows都关机时仍运行。没有云端，只在个人电脑运行，关机/睡眠就会停。

```sh
python scripts/reminder_bridge.py connect --client-id YOUR_APP_ID --tokens /private/tokens.json
python scripts/reminder_bridge.py create-list --tokens /private/tokens.json
python scripts/reminder_bridge.py tick --manifest /private/reminders.json --tokens /private/tokens.json --list-id YOUR_LIST_ID --state /private/delivery.sqlite --allow-upload
python scripts/reminder_bridge.py serve --manifest /private/reminders.json --tokens /private/tokens.json --list-id YOUR_LIST_ID --state /private/delivery.sqlite --allow-upload
```

`--allow-upload`必须来自已授权的执行，不是让助手自动绕过确认。私有令牌文件需由运行账号独占；POSIX写入使用0600，Windows还需用户目录ACL。每个账号/清单使用独立令牌和状态，多个用户不要共享这些文件。

## 云端运行示例

用户需提供或选择已授权的云主机；本模块没有自动购买服务器或默认把私有计划发给某个托管商。无公开HTTP接口，无需开放入站端口。Docker镜像只包含通用投放代码。

```sh
docker build -f cloud/Dockerfile -t baymax-delivery .
# /private/baymax须让UID 10001可读写，父目录应仅运行账号可访问。
docker run -d --name baymax-delivery --restart unless-stopped \
  -v /private/baymax:/data baymax-delivery \
  --manifest /data/reminders.json --tokens /data/tokens.json \
  --list-id YOUR_LIST_ID --state /data/delivery.sqlite --allow-upload
```

默认每60秒检查，提醒警报设置在创建后约60秒，通常有调度、网络及客户端同步延迟，不能保证秒级推送或锁屏送达。网络长时间中断后，仅投放最近15分钟内的任务，**不补入整月积压**；超期未发送任务需人工复盘。可用`--window-minutes`配置1–60分钟窗口。用户不愿上传时继续Excel或本地平台通道，不能伪称离线手机也能自动接收云消息。

## 避免重复与保存记录

- 稳定事件标记、持久SQLite和远端清单标记共同去重；重启不重新投放已发送、已完成或用户删除的事项。
- 状态中的`NULL`远端ID表示发送结果不确定；下一次检查能看到远端标记就自动确认，查不到则保留待核实，**不盲目再次POST**。`needs_attention`不为0时需要运维检查，不能声称这条已送达。
- 单个worker/清单；不支持分布式多副本。不能删除持久状态后盲目重发，也不能复制令牌给不同运行实例。
- 不覆盖远端备注、完成状态；不删除漏做任务；不把勾选推导成完整实际摄入。用户填写的记录尚未自动回传到Excel，复盘仍需用户提供。
- 从旧的134条清单迁移时，先备份用户备注和完成状态，实际验收新通道，再仅处理旧的未来任务。当前版本**不自动清空旧苹果清单**。

## 验收与停止

本地测试仅证明投放规则与去重策略。真实启用需依次验证：测试清单创建、目标手机同步、通知出现、完成后不重复、下一时段正常投放、个人电脑关机时继续投放。没有完成这些不能报告“跨平台自动提醒已接通”。停止worker即可停止后续投放；用户可在微软账号撤销应用授权。已创建任务保留给用户处理。

官方依据：[跨设备支持](https://support.microsoft.com/en-us/todo/set-up-microsoft-to-do)、[创建提醒任务](https://learn.microsoft.com/en-us/graph/api/todotasklist-post-tasks?view=graph-rest-1.0)、[设备代码授权](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code)、[刷新令牌](https://learn.microsoft.com/en-us/entra/identity-platform/refresh-tokens)。
