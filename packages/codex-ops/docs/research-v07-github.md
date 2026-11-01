# 0.7 GitHub research / GitHub 一手研究

Research date: 2026-10-29 (Asia/Singapore). Scope: read-only repository research,
not installation, runtime evaluation, or independent reproduction of third-party
benchmarks. Public GitHub resources were read through the connected GitHub app.
README claims below are distinguished from source observations and our proposals.

## 结论

0.7 最有价值的方向是减少完整任务中的往返和重复取证，并把采用率、实际 token
和成功率联结起来。继续增加工具数量本身不构成超越 dsh-ops 的证据。建议把
“自适应证据交付 + 可审计的工作流采用 + 实际成本归因”作为同一条产品主线。
这是基于下述源码与设计的判断，不是已经测得的收益。

## 上游 dsh-ops 当前到哪里

Observed default-branch HEAD: `627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa`,
2026-10-29T06:55:39Z. Latest published release returned by the GitHub API:
[`v0.4.4`](https://github.com/T-Auto/dsh-ops/releases/tag/v0.4.4),
2026-10-28T02:55:30Z. Release numbering must not be compared numerically with our
independently versioned Codex plugin. Main and released artifacts are separate.

| 已有能力 | 上游一手证据 | 对 Codex Ops 的意义 |
| --- | --- | --- |
| Minimal/Standard/PTC/Cordis preset、Windows shell 与部分官方文件工具替换 | [README](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/README.md), [components](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/docs/component-reference.md) | 这是宿主级路由优势；我们目前保留原生工具，依靠显式工作流和输出层，不能称等价原生替换。 |
| `tools_addition` 动态加载与 18-API PTC SDK；`ops_load_sdk` 按需加载 1–5 个 API | [components](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/docs/component-reference.md), [discovery source](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/src/discovery/search.ts) | 我们的薄 catalogue 与显式 SDK 已有渐进披露，但不是宿主动态工具注册。 |
| Native 紧凑文本与 PTC 类型化 Outcome 分别服务模型、程序 | [native/PTC](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/docs/native-ptc.md) | 应继续保持我们完整程序值与呈现层分离，不能为短输出改坏返回值。 |
| 文件范围读取、grep/glob、文档、CAS 编辑、批操作预检/恢复与结果引用 | [components](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/docs/component-reference.md), [batch and result contracts](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/docs/native-ptc.md) | 不是只压缩 shell 的项目；不能把已具备的批操作和引用检索误报为差异化。 |
| 可选只读 OPS sidebar / panel | [components](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/docs/component-reference.md) | 我们有诊断/统计但不能宣称已拥有 Codex 原生侧栏。 |
| Windows x64 / Linux x64 / macOS arm64+x64 原生发布材料与校验 | [runtime-bearing installation](https://github.com/T-Auto/dsh-ops/blob/627dbc2ab1c0c36a2f3be2d6a576e83ec2e314fa/docs/native-ptc.md) | 本机 Windows 验收不等于等量跨平台支持。 |

上游仍在解决同类成本问题：[#477](https://github.com/T-Auto/dsh-ops/issues/477)
请求批量并发读取，对应 [PR #478](https://github.com/T-Auto/dsh-ops/pull/478)
在查询时仍 open、未合并；不能列为已经交付。现有 `ops_read_files` 已支持 1–32
文件，提案增加的重点是并发实现而非首次批量接口。
[#474](https://github.com/T-Auto/dsh-ops/issues/474) 提供 Windows 真实语料的
grep 性能证据并区分完整扫描、`exactTotal:false` 提前停止；这是作者的实测，
本次没有复现。可借鉴其固定语料/二进制哈希/host-to-result 计时边界。

### 规划、恢复、代码执行的准确差异

| 领域 | dsh-ops | Codex Ops 0.6.1 | 0.7 应新增什么 |
| --- | --- | --- | --- |
| 编排 | 宿主 PTC 执行 + 动态 SDK 注册 | 原生 `functions.exec` + 显式 SDK + workflows | 自动形成有界证据计划并提高自然采用；不再造执行器。 |
| 独立文件批变更 | `ops_batch` plan→resume、修订预检、持久化状态 | `ops_plan` 1–32 个不相交变更，原生执行与恢复 | 不把已有批处理重复包装成新能力。 |
| 顺序依赖任务 | 单 batch 明确拒绝 overlapping/dependent targets | `ops_task` 已有 ordered stages、status/resume/cancel/rollback | 提升可发现性、必要时自动选择；单次简单写入不走task。 |
| 崩溃恢复 | pending/completed/failed/unknown，unknown 只验后置条件，同session恢复 | 已有原生执行日志和恢复契约 | 改进会话/引用生命周期和用户可解释状态，不宣称首次提供恢复。 |
| 结果取回 | 结果引用与分页 | 已有 batch(1–8)、find/outline/items/count/group、总字节预算 | 引入意图相关索引和一批查询的自动采用，而不是再加batch API。 |
| 读证据 | 原生文件/文档与紧凑输出 | 9项原生读、1–4独立read batch、4个workflow、小结果直返 | 读路径从“必须记得选工具”转为合适场景的低摩擦默认。 |
| 去重 | 本次不声称已证明跨轮语义去重 | explicit incremental + same-frame dedup | 跨轮可追溯证据复用，严格区分已存储与仍在模型上下文。 |

DSH 一列依据上方固定版本的 native-ptc/component-reference；本地一列依据
[README](../README.md)、[workflows](workflows.md) 和本次主审计对现有工具契约的核对。
DSH 文档称进度目前只有 preflight/settlement，不能说其已具每文件实时进度。

主审计另报告：排除插件开发会话后的近期业务活动中没有新 workflow 调用，0.6.1
独立业务样本的 17 次 retrieval 有 16 次 raw、13 个不同引用。这些数字由主审计
负责保留来源与时间窗，本 GitHub 子报告未独立复算；它们支持“现有结构化/批量能力
未自然采用”的调查方向，而不是继续增加重复 API。零采用也不能单独证明路由缺陷：
必须先审计其中适合工作流的实际机会。

## 相关项目

### 1. Context Mode：意图检索、批执行、会话连续性与真实 usage

Repo: [mksglu/context-mode](https://github.com/mksglu/context-mode).
Observed HEAD: `0f8ba1010411bc6b1c6b1147b4ef0c5c5e2bc694`,
2026-10-28T18:06:14Z.

- README 描述 `ctx_batch_execute` 一次执行多命令与多查询，可选并发 1–8；
  `ctx_execute` 仅把 stdout 送进上下文；带 intent 的大结果进入索引后返回相关片段。
  这与我们的 Code Mode 程序内部保留原始值有相近目标，但执行环境和安全边界不同。
  [README](https://github.com/mksglu/context-mode/blob/0f8ba1010411bc6b1c6b1147b4ef0c5c5e2bc694/README.md)
- README 的搜索设计使用 SQLite FTS5、BM25、porter/trigram、RRF、标题权重与邻近
  重排。可以启发我们的结果引用采用相关证据优先、一次多查询，避免先看无关预览再取回。
  本次未运行其性能/召回测试；不能直接引用 README 的节省比例为我们的预期。
  [README](https://github.com/mksglu/context-mode/blob/0f8ba1010411bc6b1c6b1147b4ef0c5c5e2bc694/README.md)
- 源码明确记录 Codex rollout 的 `event_msg/token_count`，并区分累计
  `total_token_usage` 与增量 `last_token_usage`。这是本机总 token 归因的直接参考，
  不需要把输出字节除以 4 冒充实际 usage。
  [usage.ts](https://github.com/mksglu/context-mode/blob/0f8ba1010411bc6b1c6b1147b4ef0c5c5e2bc694/src/adapters/codex/usage.ts)
- 源码的搜索限流按 agent-context 分桶，修复了多 agent 共用 MCP 时互相耗尽全局预算
  的问题；对我们的并行编排与采用率统计很有价值。
  [flood-guard.ts](https://github.com/mksglu/context-mode/blob/0f8ba1010411bc6b1c6b1147b4ef0c5c5e2bc694/src/search/flood-guard.ts)
- README 宣称通过多种 hooks 持久化事件并恢复工作状态。Codex adapter 源码也明确
  标注宿主版本和 hook 限制，包括 PostToolUse 输出覆盖不被支持。我们应读取当前
  本机原生协议验证，不把该项目 README 的兼容表当官方保证。
  [hooks.ts](https://github.com/mksglu/context-mode/blob/0f8ba1010411bc6b1c6b1147b4ef0c5c5e2bc694/src/adapters/codex/hooks.ts)

### 2. RTK：领域压缩、遗漏机会与采用率

Repo: [rtk-ai/rtk](https://github.com/rtk-ai/rtk).
Observed HEAD: `7e92da00a5cf737dc87850505aa3dea603454613`,
2026-10-28T23:54:21Z.

- README 列出 git、测试、lint、构建、容器等领域过滤：例如折叠成功测试、保留失败，
  grep 按文件归组。应按我们的未覆盖噪声占比选择适配器，而不是复刻全部命令。
  [README](https://github.com/rtk-ai/rtk/blob/7e92da00a5cf737dc87850505aa3dea603454613/README.md)
- `rtk gain`、`rtk discover`、`rtk session` 分别回答已节省多少、哪些机会漏掉、
  最近会话的采用率。我们最值得学的是这个可衡量闭环，不能只报 workflow 总次数。
  [README](https://github.com/rtk-ai/rtk/blob/7e92da00a5cf737dc87850505aa3dea603454613/README.md)
- README 明说其 token 是 `bytes/4` 估算，bash 输出只是输入的一部分，输入又只是账单
  的一部分。本报告不把其节省比例解读为实际模型账单下降。
  [How Savings Work](https://github.com/rtk-ai/rtk/blob/7e92da00a5cf737dc87850505aa3dea603454613/README.md#how-savings-work)
- 新的 pipeline engine/proxy 部分采用 BUSL-1.1；README 的 provider proxy 目前说明
  实证重定向入口是 `rtk claude`。不应把它当作现成 Codex 原生集成，或直接复制所有
  实现。借鉴可配置策略与测量方式即可。
  [README](https://github.com/rtk-ai/rtk/blob/7e92da00a5cf737dc87850505aa3dea603454613/README.md)

### 3. Lossless Claw：原文持久化与可回溯摘要图

Repo: [Martian-Engineering/lossless-claw](https://github.com/Martian-Engineering/lossless-claw).
Observed HEAD: `b00ffb94f0f8889f245864c7075e9821a3c739b8`,
2026-10-27T16:08:03Z.

- README 描述在 SQLite 保存原消息，把较旧消息汇总成 DAG，组装近期原文与历史摘要，
  并通过 `lcm_grep/lcm_describe/lcm_expand` 回到原始证据。
  [README](https://github.com/Martian-Engineering/lossless-claw/blob/b00ffb94f0f8889f245864c7075e9821a3c739b8/README.md)
- “lossless” 指原文可恢复，不意味着摘要在模型当前上下文里无损。其摘要需要额外模型
  调用，README 给出摘要模型、调用频率、超时与花费退避设置。我们应先做确定性证据
  索引、修订指纹与显式展开，再考虑带净收益门槛的模型摘要。
  [README](https://github.com/Martian-Engineering/lossless-claw/blob/b00ffb94f0f8889f245864c7075e9821a3c739b8/README.md)
- 它依赖 OpenClaw 的 `contextEngine` 插槽，不是可直接移植到 Codex 的输出 hook。
  0.7 可借鉴“可回溯证据图”，不承诺接管 Codex 原生上下文装配。
  [configuration](https://github.com/Martian-Engineering/lossless-claw/blob/b00ffb94f0f8889f245864c7075e9821a3c739b8/README.md#configuration)

### 4. Cloudflare Code Mode：一次程序编排多工具

Package: [cloudflare/agents/packages/codemode](https://github.com/cloudflare/agents/tree/main/packages/codemode).
Observed repository HEAD: `786d30e305baebc5fbf5ad5ed80461f88a728468`,
2026-10-28T17:15:23Z.

README 说明从工具生成 TypeScript 类型，模型编写 JavaScript，在隔离 Worker 中一次
编排多个操作；包明确标记 experimental。
[README](https://github.com/cloudflare/agents/blob/786d30e305baebc5fbf5ad5ed80461f88a728468/packages/codemode/README.md)

Codex 的 `functions.exec` 已有这一关键机制，我们无需另造任意代码执行器。
可创新的部分是为真实任务生成短而稳定的证据计划、批量读依赖、进度/失败结构、
结果预算与一次返回。不要把“新增 JavaScript SDK”本身当成比现有宿主更先进。
此为根据现有 Codex Ops 0.6.1 工作流契约作出的设计判断。

## 面向 0.7 的建议（设计，不是已实现）

| 优先级 | 建议 | 机制与验收重点 |
| --- | --- | --- |
| P0 | 采用率与净成本账本 | 记录候选场景→提示/路由→采用→成功→取回→fallback；按真实任务、会话、版本、agent 分层，排除验收/当前审计，join 原生 token_count，禁止累计值重复求和。 |
| P0 | 任务级证据计划 | locate/diagnose/documents 扩为有界并行证据组合，一次提供位置、相关源码、根因候选与缺失证据；候选只排序、不给无证断言。比较完整任务成功率和往返数。 |
| P0 | 意图驱动的自适应交付 | 依据任务查询、内容类型、消费方式和取回历史，在 exact inline、结构化证据、引用三种表示中选净成本最小者；小内容不封装成第二次取回任务。 |
| P1 | 可回溯证据索引 | 对已有授权结果分块索引，保存来源、版本/修订、coverage、权限上下文；一次多查询，恢复原文。相似内容只助排序，不直接复用可能过期的工具答案。 |
| P1 | 自适应进度与领域诊断 | 按真实高占比命令处理重复进度、测试/构建/搜索输出；等待只返回变化或完成/失败证据。始终保留原始退出状态、句柄、完整结果。 |
| P1 | 工作状态与成本可视化 | 展示工作流漏用原因、重复读取、引用返工、模型 token 与非缓存 token；会话恢复提供带来源的确定性状态卡，避免无条件新增模型摘要成本。 |

“已见过”不是“仍在模型上下文”。跨回合自动省略正文应有可验证的会话/上下文代际
和有效证据指纹；如果宿主没有可靠保留信号，就返回短摘要+可展开引用，不能静默隐藏。
这与当前 [context-boundaries](context-boundaries.md) 保持一致。

发布门槛建议同时覆盖：任务正确率、总原生动作数、外层模型交互轮次、累计实际输入/
缓存/非缓存/输出 token、取回成本、墙钟时间、失败/恢复、CRAP ≤6。采用率不是越高越好：
单次已知读取、写入和轮询适合原生工具，应从“适合工作流”的分母中排除。

## English summary

The strongest 0.7 opportunity is a measurable evidence-delivery loop, not a larger
tool catalogue: count eligible tasks and missed opportunities; join native model
usage; combine dependent evidence into fewer model round trips; and choose exact
inline data, bounded relevant evidence, or a retrievable reference based on net cost.

DSH retains native preset/tool replacement, dynamic SDK loading and sidebar
advantages. Context Mode contributes retrieval and Codex usage-attribution designs;
RTK contributes missed-opportunity/adoption analysis and domain filters; Lossless
Claw contributes recoverable evidence graphs; Cloudflare Code Mode reinforces
programmatic orchestration already available in `functions.exec`. None of their
README savings figures proves a Codex Ops improvement. The proposed release must
measure completed tasks and total model usage while preserving permissions,
original return values and recoverable evidence.
