# 系统日历：设备组合、连接与验收

默认不绑定任何厂商账号。手机操作系统决定接收能力，电脑系统主要影响安装命令。先问用户已有的设备与日历，不要先让所有人注册微软或Google。

## 三种路径的实际差别

| 路径 | 需要什么 | 计划修订 | 提醒 |
|---|---|---|---|
| CalDAV写入专用云日历（优先持续更新） | 用户已有支持CalDAV的服务/自托管服务，用户自己的认证 | 连接后保存个人计划会自动排队更新；CLI可手动同步 | 手机同步到系统日历后由系统提醒；须实测 |
| HTTPS日历订阅（兼容分支） | 私有托管、用户授权、接收日历支持订阅 | 客户端定期刷新，无法保证即时 | 有些客户端忽略外部VALARM，不作为准点默认方案 |
| ICS文件导入（免账号兜底） | 手机能接收文件，日历支持导入；某些安卓需兼容导入工具 | **不会自动更新**；重导可能重复 | 导入到本地后可离线提醒，仍取决于客户端 |

不能同时承诺“零账号、零安装、无需联网、所有品牌、自动跨设备更新”。缺少某项能力时，列出当前设备可用的分支，让用户选；不能用微软客户端掩盖系统日历不兼容。当前实现提供ICS与CalDAV，**没有自动购买/部署订阅托管服务**。

## 四平台的15种非空组合

Mac=M，Windows=W，iPhone=I，安卓=A。全部组合如下；没有手机的3种组合只能先在电脑看计划，不能声称已在手机接收。手机单独使用时可接收计划与日历，但没有本地Codex运行环境就不能在该手机运行这个skill。

| 用户设备 | 制作/修改 | 手机接收路径 |
|---|---|---|
| M | Mac运行skill | 无手机；Mac日历/本地计划 |
| W | Windows运行skill | 无手机；网页计划/兼容桌面日历 |
| I | 已授权远程skill或接收别人为自己生成的文件 | iCloud/系统CalDAV或兼容ICS导入 |
| A | 已授权远程skill或接收自己的计划文件 | 已有日历；必要时CalDAV同步器或ICS导入工具 |
| M+W | 两台电脑共用一份权威计划/状态 | 无手机；避免双端同时写同一周期 |
| M+I | Mac | iCloud或系统CalDAV；也可ICS |
| M+A | Mac | 安卓已有日历/CalDAV同步器；也可ICS |
| W+I | Windows | 同一iCloud/CalDAV专用日历；无需Mac，或ICS |
| W+A | Windows | 同一CalDAV日历/已有安卓账号能力，或ICS |
| I+A | 已授权远程运行环境 | 共用CalDAV日历，两端分别接入；无远程则接收ICS |
| M+W+I | 任选一台为编辑主端 | iPhone同一日历 |
| M+W+A | 任选一台为编辑主端 | 安卓同一日历 |
| M+I+A | Mac | 两手机共用CalDAV日历，各自验收 |
| W+I+A | Windows | 两手机共用CalDAV日历，各自验收 |
| M+W+I+A | 一份权威计划/同步状态 | 所有客户端接同一日历，两个手机分别验收 |

这张表是接入设计，不是15组真机已测试的声明。当前网页仅本地，未提供可直接手机访问的公开编辑服务。`127.0.0.1`在手机表示手机自己，不能给手机当订阅网址。多电脑并发编辑、手机编辑、公开多用户账户均需要另行实现安全的共享服务；现在可在一台主机编辑，其余设备收日历。

## 已有服务优先

- **iPhone / Mac**：已有iCloud可使用专用日历；也可在系统账户设置添加CalDAV。iCloud第三方程序认证通常需双重认证与应用专用密码。用账户官方页面完成，助手不索要聊天明文密码。用provider的实际CalDAV discovery定位集合，不猜用户ID或固定的`pXX`主机。
- **安卓**：先检查厂商日历。可通过DAVx⁵等同步器写入Android Calendar Provider，让已有系统日历显示；不强制Google服务。某些设备的系统日历不显示第三方账户，需要用户选择兼容日历。应用分发渠道、费用、地区可用性按当时情况说明，不能假定免费或预装。
- **Windows**：Python脚本可以直接更新远端CalDAV；不要求Windows系统有CalDAV日历。想同时看日程，可用用户已有客户端或Thunderbird等CalDAV客户端。脚本标准库跨平台，IANA时区在Windows用tzdata。
- **Nextcloud / Radicale / 其他CalDAV**：可接现有服务或用户授权的自托管服务，需HTTPS与专用日历。本版实现Basic/app-password认证和条件PUT；使用OAuth-only、厂商私有接口的服务不是“填个地址就兼容”，需匹配现有连接器或改走ICS。
- **Google / Outlook**：已有用户可继续使用对应官方日历及其导入/订阅能力，但本版不包含其OAuth日历写入适配器。不能假称通用CalDAV脚本已支持所有这些服务。

## 连接与自动更新

先生成可审阅计划，再确认目的账号/专用日历，以及上传详细步骤还是只上传通用标题。用户已经授权的同一目的地、同一字段范围无需每次修订重复确认。凭据在用户本机私有环境中配置，不能放聊天、GitHub、网页表单或shell历史中的明文命令。

私有配置文件示意（占位值要换成实际账号/集合）：

```json
{
  "calendar_url": "https://calendar.example.org/dav/user/baymax/",
  "username": "YOUR_ACCOUNT",
  "password_env": "BAYMAX_CALDAV_PASSWORD",
  "include_details": true
}
```

密码通过环境变量或用户选择的安全凭据管理方式供给；配置中的`password_env`仅为环境变量名。Windows同时限制文件ACL，POSIX私有文件目录使用仅当前用户权限。应用专用密码的访问范围由服务商控制，不一定只限一个日历。

`inspect`发送只读PROPFIND，输出显示名、principal、home与calendar集合线索。起始服务地址→principal→calendar-home→具体calendar URL依服务返回逐步定位。重定向不携带凭据自动跟随；需要根据官方发现结果确认新HTTPS域名后配置。命令输出中账户路径可能含身份，不复制到公共报告。

```sh
python scripts/calendar_sync.py inspect --config /PRIVATE/caldav.json
python scripts/calendar_sync.py sync --plan /PRIVATE/life-v1.json --config /PRIVATE/caldav.json --state /PRIVATE/sync-state.json --allow-upload
```

连接确认后以以下参数启动社区，**每次保存通过冲突检查的计划都会自动排队同步**，无须另行导出再传：

```sh
python community/server.py --database /PRIVATE/community.sqlite3 --calendar-config /PRIVATE/caldav.json --calendar-state-dir /PRIVATE/calendar-state --allow-calendar-upload
```

后台串行处理，最新保存的版本会排队，重启恢复未完成任务；网页显示排队、同步中、云端接受、失败或冲突。失败不无限盲重试；排查后保存新版本重试。桌面只需在生成/修改并同步时在线；未来30天已同步进手机，电脑关机后由手机日历提醒。若手机还没同步、账号断线或权限关闭，不能承诺收到新修订。

## 更新、删除与时间规则

- 完整30天按日期展开，IANA时区逐日转换成UTC，跨夏令时保持本地时刻；落在跳过/重复时刻的安排拒绝生成，要求换时间。
- UID稳定，SEQUENCE递增；同一事件更新原资源。ETag/If-Match/If-None-Match保护远端并发修改。
- 只维护当前计划在状态文件记录的资源；不扫描删除整个日历。不删过去事件，不自动重建用户已删事件。已移除的未来步骤仅在ETag吻合时删除。
- 远端手工修改产生冲突，保留原文和用户备注；助手与用户核对哪个版本为准后再作修订。不把日历手改直接当成营养或实际摄入真相。
- 写入超时可能已被服务接受，重试先GET核对同UID。服务器重排ICS内容且无法确认等价时保守报冲突，不重复POST。同步状态丢失时不可盲目清空远端。
- 一份同步状态只能用于一个账号/日历/计划。锁文件防并发；异常断电留锁时先确认没有同步进程和远端结果，再清锁。跨电脑不要各自维护同周期的不同副本。
- 冲突导致部分未更新时明确报告，不声称整个30天全部同步成功。

## 免账号导入与订阅

```sh
python scripts/calendar_sync.py export --plan /PRIVATE/life-v1.json --out /PRIVATE/life-v1.ics
# 不上传任务详情的版本：
python scripts/calendar_sync.py export --plan /PRIVATE/life-v1.json --out /PRIVATE/private-title.ics --private-titles
```

在专用Baymax日历中导入，避免与用户全部日程混在一起。文件传输方式由用户选，不擅自通过邮件、公开链接或第三方分享健康详情。不同客户端重复导入行为不同；不能依赖ICS UID保证导入器幂等。更新快照时保留备注与记录，用户知情后仅替换该独立导入日历。

需要HTTPS订阅时另选用户授权的托管位置，使用不可猜且可撤销的私有链接、HTTPS和缓存刷新策略；订阅链接本身能暴露日程，不能放公共GitHub。没有部署前只能说“已生成可供托管的ICS”，不能说“订阅已启用”。优先CalDAV避免订阅刷新延迟。

## 验收分层

1. 本地：30天日期、来源、重复/冲突、稳定UID、UTF-8折行、VALARM、时区、修订和真实记录保留。
2. 远端：专用测试日历创建一条事项，确认返回、读回内容、更新不重复、删除仅影响自己的未来测试事项。
3. 手机：每台目标手机显示标题/时间/步骤，允许通知；设几分钟后提醒，锁屏观察。安卓同时检查省电、后台同步和厂商通知设置。
4. 修订：改时间、移除未来步骤、远端手工写备注，再同步验证冲突保护。
5. 离线：电脑关机后手机已有事件仍提醒；手机恢复联网后接收后续修订。不能把网络传输保证说成锁屏通知保证。

不把浏览器手机尺寸测试当真机验收。本项目尚未完成真实iCloud/CalDAV账号与Mac/Windows/iOS/安卓组合的通知验收。

资料：2026-10-08读取了 [Apple多日历说明](https://support.apple.com/guide/iphone/set-up-multiple-calendars-iph3d1110d4/ios)、[DAVx⁵官方说明](https://www.davx5.com/manual/introduction.html)、[Thunderbird日历说明](https://support.mozilla.org/en-US/kb/creating-new-calendars)。协议入口：[RFC 5545](https://www.rfc-editor.org/rfc/rfc5545)、[RFC 4791](https://www.rfc-editor.org/rfc/rfc4791)。文档可用不等于用户设备已验证。
