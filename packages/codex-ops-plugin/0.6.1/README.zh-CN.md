# Codex Ops 0.6.1

新增日志路径诊断和小文档结果直返，减少可避免的回读步骤。
实测成本及限制见 [0.6.1 验收记录](docs/release-0.6.1.zh-CN.md)。

将 dsh-ops 的完整值与模型呈现分离接入本机 Codex，合并查询流程、保留有效证据，
并记录回读成本。英文见 [README](README.md)。

## 工具与使用方式

| MCP 工具 | 用途 |
| --- | --- |
| `ops_capture` | 存档大结果并提供有界预览，保留 Code Mode 内部完整值。 |
| `ops_result` | 检索、定位、计数、分组保存的数据，批量查询多个引用而不重跑源操作。 |
| `ops_files` | 读取、搜索并返回上下文、检查、grep、glob、stat、diff 和受支持文档提取。 |
| `ops_catalog` | 先列出能力，再按需提供某项操作的 schema、示例和恢复指引。 |
| `ops_plan` | 预检 1–32 项不重叠修改，保存绑定版本的计划，返回原生执行参数。 |
| `ops_stats` | 查看桥接、缓存、来源归因、回读成本和选定时段的统计。 |
| `ops_workflow` | 组合定位与上下文、日志诊断、文档证据和显式增量读取；提供可调用的 Code Mode SDK。 |
| `ops_task` | 规划有顺序依赖的文件/目录修改，返回状态、取消、恢复与回滚的原生命令。 |

收集多类证据时优先使用[组合工作流](docs/workflows.zh-CN.md)。
`ops_catalog(operation="workflows")` 提供 JavaScript helper 和参数类型；
`ops_catalog(operation="task")` 提供分阶段结构、目录边界与
[原生任务生命周期](docs/tasks.zh-CN.md)。工具仍通过 MCP 发现，helper 不代表
已实现原生工具注册表的动态替换。

使用 `ops_files(operation="search")` 可一次完成 grep 和命中附近的源码读取。
重叠范围会合并，结果保留行号、版本、覆盖范围、遗漏和续读信息。搜索与重读不是
文件系统原子快照：命中行会再次比对，并标为未变、已变或不可用。两阶段共用有界
时限，不自动重试。详见[查询契约](skills/compact-output/references/query.zh-CN.md)。

九项原生只读操作保留 worker 的路径、凭据和链接限制。独立只读 batch 接受 1–4
项请求，保持顺序和各项结果；文档支持 CSV/TSV、DOCX 和受限文字层 PDF。
见[文件参数](skills/compact-output/references/files.zh-CN.md)。参数不熟悉时使用
[能力目录](skills/compact-output/references/catalog.zh-CN.md)：默认只列能力，选择后
才返回精确参数结构和边界。这是按需文档，不等同于原生 SDK 动态注册。

## 渐进检索

`outline` 列出子项 JSON 指针；`find` 返回字面命中的指针、行号和有界扫描范围。
`items` 支持路径选择、字段投影和记录筛选；`count` 统计匹配记录，
`group` 按一个标量字段聚合。`raw` 返回精确文字或原始 JSON，偏移按 Unicode
字符计算，页面大小由 `max_bytes` 控制，行数参数 `limit` 不限制 raw 正文。

`ops_result(action="batch", requests=[...])` 可在一次调用中查询 1–8 个缓存视图，
共用 512–16000 字节的总 `max_bytes` 预算。每项保留独立结果、错误、续读与
完整性信息，不执行任何源操作。按 `nextOffset` 续读并检查 `scanComplete`；
保存视图完整不代表源数据完整。有界检索页和查询批次不会被再次自动压缩。

## 通过原生权限执行修改

`ops_plan` 只读取并缓存计划，不修改工作区。实际执行需将返回的
`nativeExecution` 参数交给 Codex 原生 `exec_command`，沿用真实沙箱与审批。
计划或引用不授予执行权限，MCP 不启动修改执行器。

write、edit、精确数量 replace、copy、move、remove 使用版本校验、整批预检
和持久恢复快照。单文件上限 1 MiB、计划上限 8 MiB；父目录需存在，路径不能
重叠，传输目标需不存在。整个批次不是跨文件原子事务。遇到不确定结果，先检查
状态，再显式续做或回滚，不重复 apply。日志位于根目录的
`.codex-ops-mutations/`，含原文件字节；恢复保证内容与存在状态，不保证所有
文件系统属性。详见[修改契约](skills/compact-output/references/mutations.md)。

## 自动呈现与上下文证据

`ops_stats.runtimeBridge.activeForThisProcess` 为 true 时，普通
`text(raw)`、`notify(raw)` 即可使用经版本验证的 Windows 桥接。JavaScript
内部完整值保持原样；未启用桥接时仍可显式 capture。

通用阈值保持为结构化 JSON／shell 2 KiB、普通文字 8 KiB。更小的已完成 shell
输出只有命中明确语义类型且收益足够时才精简。成功日志、失败和 diff 各自保留
相关证据；源码或文档不会仅因出现 error 字样就被视为诊断日志。原始文字仍可
取回，变化的终态和原生诊断保持完整。运行中重复进度及同一次 Execute／Wait
返回中的精确重复文字可复用引用。

跨模型步骤读取去重仍未启用：历史记录、文件版本和 window ID 都不足以证明
旧正文仍在当前模型请求中。见[上下文证据](docs/context-boundaries.zh-CN.md)。
直接 Bash hook 需要匹配的成功完成记录，失败、运行中及无法核验的状态保持
原生返回。媒体保持原样，不修改 Codex 可执行文件或安装模型／API 代理。

## 统计、面板与存储

呈现统计按通道、原因、工具和会话散列记录 UTF-8 字节。Code Mode 身份与 MCP
聊天身份是不同维度，未知或有歧义的来源保持未归因。成功回读和重复页请求独立
计量；这些结果随后可能再次被呈现，不能将两组字节相加减来宣称净上下文收益。

`window="all"` 保留实例累计口径；`hour`、`day`、`week` 选择已完成的
五分钟桶，当前不足五分钟的数据暂不计入。采集起点、实际区间及有界历史丢失
明确显示，不伪造旧版分桶数据。近期桶在固定存储上限内保留七天。日常与验证
分账，计数不记录命令或正文。

用 `python dashboard.py --output C:/absolute/stats.html` 导出离线页面，
可选 `--window hour` 和明确的 `--tasks-root` 查看保存的修改日志阶段。
`--serve` 显式启动前台只读回环服务，支持手动刷新，不自动启动。日志阶段
不代表已重新验证当前文件。详见[面板说明](docs/dashboard.zh-CN.md)。

观察结果存入本地 SQLite：单条上限 10 MiB、逻辑配额 100 MiB、保留 24 小时。
新原生 MCP 引用绑定聊天与可取得的权限元数据；自动输出引用绑定运行时，旧引用保留
原归属。详见[引用与重启边界](docs/session-scope.zh-CN.md)。原始结果可能含敏感正文，
不上传、不加密、不保证安全擦除。用完可释放引用；过期不能成为重复副作用的理由。

## 安装与验证

通过 `codex plugin add codex-ops@personal --json` 安装，在 `/hooks` 审阅
具体定义；运行时更新后重启桌面。更新源目录和版本，不编辑插件缓存。
MCP、hooks 与桥接共用专属 uv 环境。见[部署与回退](runtime_bridge/README.md)
和[质量说明](QUALITY.md)。

原生协议、真实 worker 和固定工具轨迹检查完整值、输出预算与操作结果。
当前测试数量及函数级 CRAP 见[质量报告](verification/quality/crap.md)。

0.6 评测包含定位、修复、批量修改、日志诊断和文档证据五个领域的 20 项不同任务，
每项重复两次，比较原生 Codex、冻结的 0.5 与 0.6。结果通过原生沙箱独立检查；
保留失败、缺失用量、原始校验结果，以及有明确理由的后续重新校验。
阅读[比较报告](verification/v06-model-comparison.json)时须连同有效性字段一起看，
输出字节下降本身不代表 token、费用或耗时下降。各版本 skill 与 SessionStart 指引
通过 developer instructions 提供，属于等价指引，不声称每项试验都触发了真实 hook 事件。

原生命令通过有界只读缓存快照加载计划，不在源缓存创建 SQLite/WAL 文件。
活动写者可能使引用在执行前暂时不可用。worker 的元数据保留要求可能超出
Windows workspace-write 权限；拒绝与日志状态会被保留，不降级权限。

原生插件单独打包描述文件、hooks、skills 和文档，开发虚拟环境与私有验证轨迹不再复制进插件缓存。运行命令仍指向已验证的本机源码，使用原有专属 uv 环境。
