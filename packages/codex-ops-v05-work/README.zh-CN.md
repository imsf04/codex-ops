# Codex Ops 0.5.0

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
随机引用是本机用户的持有式能力，不是跨聊天授权隔离。原始结果可能含敏感正文，
不上传、不加密、不保证安全擦除。用完可释放引用；过期不能成为重复副作用的理由。

## 安装与验证

通过 `codex plugin add codex-ops@personal --json` 安装，在 `/hooks` 审阅
具体定义；运行时更新后重启桌面。更新源目录和版本，不编辑插件缓存。
MCP、hooks 与桥接共用专属 uv 环境。见[部署与回退](runtime_bridge/README.md)
和[质量说明](QUALITY.md)。

原生协议、真实 worker 和固定工具轨迹检查完整值、输出预算与操作结果。
Windows 沙箱已通过原生设置流程恢复就绪。真实模型试验已完成：使用
`gpt-6.1-terra`，每项任务、每种条件各执行一次，没有重试。独立检查结果为
**基线通过 4/5，启用后通过 5/5**，覆盖代码定位、测试修复、批量修改、
日志诊断和文档／表格查询。详见[配对报告](verification/real-model-comparison.json)、
[基线记录](verification/real-model-baseline.json)和
[启用记录](verification/real-model-enabled.json)。

只有两边均成功的测试修复任务保留了可比的工作区布局和完整资源记录：总 token
从 **409,938 降至 255,490（减少 37.68%）**，耗时却从 **72.323 秒增至
154.154 秒（增加 113.15%）**。总 token 包含缓存输入，不等同于计费成本。
基线批量修改任务的资源指标缺失；启用组后三项任务是在只读计划加载修复、
临时目录及缓存权限布局调整后执行，因此不计算这些配对的节省比例。外部检查器
遇到读取拒绝后，已有输出通过同一原生 workspace-write 沙箱重新检查；
没有重新运行模型，原始检查失败记录仍保留。

启用条件包含候选桥接层和六个 MCP 工具，没有加载插件 skill 或 SessionStart
指引；只有代码定位任务实际使用了 MCP 工具。这次小样本、混合配置试验不能证明
普遍的成功率、成本或速度改善，也不能区分两个组件各自的贡献。运行顺序、缓存、
系统负载和模型非确定性同样影响测量。测试数量见
[当前质量报告](verification/quality/crap.md)。
输出字节减少本身不证明 token 节省、任务更快完成或成功率提高。

修改计划的原生加载现在使用有界只读缓存快照，不在源缓存创建 SQLite/WAL 文件。
缓存有活动写者时可在执行前返回不可用。原版 worker 的元数据保留要求可能超出
Windows workspace-write 的权限，届时保留拒绝和审计状态，不降级权限；可按任务
需要使用已经获准的原生编辑工具。
