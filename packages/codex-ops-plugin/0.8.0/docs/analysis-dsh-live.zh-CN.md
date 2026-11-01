# DSH / dsh-ops 本机真实使用审计

日期：2026-10-30。只读调查已有日志；没有运行新的 DSH 任务、修改 DSH 配置或升级插件。

## 日志与当前安装

- 会话目录：`C:\Users\imsfp\.dsh\sessions`，共120份 `session.v4.jsonl.zstd`，使用 Python3.14标准库 compression.zstd 与 json 读取，120份均解析成功。
- 有工具调用的会话114份，按日志事件时间覆盖新加坡时间2026-10-17晚至2026-10-30 02:14。106份出现过 OPS 调用，覆盖约93.0%。这不是适用任务机会的采用率。
- 当前 desktop 安装的 `node_modules/dsh-ops/package.json` 是0.3.0。当前 cordis.yml 启用了 dsh-ops-shell、dsh-ops-file；dsh-ops-ptc、dsh-ops-background 被禁用。headless 对应 node_modules 路径没有该插件。
- 当前配置不能证明所有历史会话运行同一插件版本。这些日志不代表上游当前0.5.0完整能力，也不是0.5与Codex Ops0.7的对照实验。

## 实际调用分布

外层与内部调用是两个层次，不能相加作为模型往返次数。

| 观察 | 次数 |
| --- | ---: |
| 外层工具调用 |20,690|
| 其中 run_code |19,460|
| PTC内部派发 |32,765|
| 外层与内部出现的 OPS 调用 |13,681|
| 其中 ops_bash |13,114|
| ops_grep |267|
| ops_replace |128|
| ops_inspect_local_file |109|
| ops_glob |63|

OPS 调用中95.9%是 ops_bash。PTC内部仍大量使用 DSH原生 read6,578次、edit5,129次、write2,763次、pwsh1,471次。当前禁用的 dsh-ops PTC 组件与这一使用形态一致；不能将这些 read/edit/write 算成 OPS SDK调用。

114份有工具的会话，初始 preset 107份ptc、7份standard；会话中可能切换，不能以初始值取代逐事件判断。工具替换、发布与指导会影响选择，因此93%的会话覆盖不代表模型在同等候选中主动偏好插件。

## 三个真实样本

| 会话 | 外层调用 | 内部PTC调用 | 已观察OPS |
| --- | ---: | ---: | --- |
| Rhino db1bcfbf… |194次run_code|232|154次ops_bash|
| RPU 18964351… |312|0|309次ops_*，包括230次ops_bash|
| 教程/幻灯片 a73fe82d… |73次run_code|151|48次ops_bash|

这些是实际工作会话；默认工作目录中的样本也可能是业务任务，不能仅按目录归为插件开发。

完整来源与seq编号见[调用链报告](research-dsh-real-chains.md)。

- Rhino seq614的一个 run_code 内完成 read、edit、ops_bash三次工具调用，seq621一次交付结果。模型不需要在每一步之间接收完整工具输出。
- Rhino seq606/609/610：原生 job_output 返回49,931字符，代码只打印状态和末尾800字符，外层810字符。属于PTC代码选择呈现；不能把这次缩短归为dsh-ops压缩器的收益，更不能外推token节省。
- Rhino seq939/941/942：ops_bash返回49,932字符，代码截到6,000字符，但搜索混入生成的覆盖率/压缩JSON。截短不保证留下最相关证据。
- Rhino seq251/254/258：请求设置约9分钟等待，宿主120秒超时，随后补轮询。超时参数与宿主实际限制仍有摩擦。
- 幻灯片 seq376/382/383：内部退出码1但isError=false，外层只打印stderr而丢掉明确退出码。随后修复代码并成功保存。业务命令失败与插件故障必须分开统计。

## Token 与历史裁剪

记录到21,062条assistant usage。逐条验证均满足：

`inputTokens + cacheReadTokens + cacheWriteTokens + outputTokens = totalTokens`

累计字段为：inputTokens44,799,098；cacheReadTokens3,706,313,344；outputTokens19,877,293；cacheWriteTokens0。这种记录格式的inputTokens不包含cacheReadTokens，不能直接与Codex“含缓存输入”字段比较。数值是跨会话、跨请求反复计入的累计实耗，不是单次上下文大小或插件节省量。

日志还记录872次 compaction/prune，shadowedTokenCount合计3,745,374；对应872条重复tool/result callId，是宿主更新历史显示面的记录。不能把更新前后结果都算作同时显示的输出，也不能将裁剪量当作插件净省token或账单收益。

调用ID、PTC子调用ID无重复；assistant message ID在会话内及跨会话均未重复。缺少同任务关闭插件的对照、端到端成功标签以及逐版本快照，因此无法给出可靠的“节省了多少token”“任务成功率”或“比Codex Ops快多少”。

## 对 Codex Ops 的启发

1. 原生入口与默认路由决定能否常用。DSH的大量使用来自熟悉的shell入口及宿主发布策略。Codex应降低进入插件的额外决策，并保持原生权限。
2. 在一次Code Mode调用里组合依赖步骤，保留程序内完整值，向模型交付紧凑结果；同时优先保留exitCode、状态与错误，避免手写slice丢证据。
3. 查询时排除无关生成物、按意图找到文件与测试，比末端截短更有价值。保留原文恢复入口。
4. 宿主历史裁剪与输出压缩是不同机制。应单独跟踪，不能将DSH宿主能力归给dsh-ops。
5. 当前日志主要支持OPS shell路径的高使用量；不能用它证明未启用的新PTC SDK、工作集或复杂工作流已经被广泛采用。下一轮评估必须记录实际版本、组件状态和任务机会。

证据：[完整聚合](../verification/dsh-real-usage.json)、[汇总与限制](../verification/dsh-real-usage-summary.json)、[事件去重检查](../verification/dsh-event-identity.json)、[调用链](research-dsh-real-chains.md)。[English](analysis-dsh-live.md)。

