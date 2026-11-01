# 0.6.0 生效与工作流采用调查

日期：2026-10-29。正式版本仍为 0.6.0；本轮候选没有安装或替换当前进程。

## 实际生效

当前 Desktop 的 manager PID 42800、native host PID 32464 均属于 0.6.0。包版本、配置版本、进程版本一致；29 个 staged 文件哈希通过，8 个 MCP 工具可发现。SessionStart/PostToolUse 两项 hooks 启用且 trusted。9,731 字节真实输出自动生成引用，回读所得 9,569 个字符与 functions.exec 内部保留的原始字符串完全相同，原 exit_code=0 保留。实际 locate 工作流调用也成功。安装记录已经更新 activeDesktopVerified=true、restartRequired=false。

证据：[实际桌面验证](../verification/desktop-live-0.6.0.json)。

## 历史零采用：事实与推断

原 120 次评测的 v06 组有 40 次任务，8 个工具均通过服务端发现检查。重读全部该组 item/completed 轨迹，实际只有 ops_result 5 次和 ops_catalog 3 次，另有 170 次原生命令；没有 ops_workflow/ops_task 调用。三次目录查询都是 workflows，响应各 6,579 字节，其中 JavaScript SDK 源码 3,655 字节；之后模型仍走原生命令。因此历史零采用不是统计漏算。工具存在不等于会被主动选择；这些轨迹支持入口摩擦这一解释，不能证明模型选择的唯一原因。

自动压缩是桥接层输出处理，workflow 则需要模型选择调用；SDK 只是显式工厂，没有注册为原生默认执行路径。旧说明还同时推荐 ops_files.search 与 ops_workflow.locate，常用参数隐藏在通用 args 和 SDK 类型后面。小任务通过原生 shell 已能完成。旧评测没有针对重复范围读取、依赖阶段及中断恢复构造任务，因此 incremental 和 ops_task 的零采用不能独立视为故障。

## 路由 A/B

同一 gpt-6.1-terra、同一 0.6.0 工具和 runtime、原有三个 fixture（定位、日志、文档），每个重复两次，两组交错，总计 12 次。用户任务未要求使用插件；干预只改变开发者说明：从完整 skill 加 hook，改为短场景路由、可直接调用参数和原 hook。原说明 hash 与历史评测完全相同。保留所有已付费尝试，无失败重跑。

| 指标 | 原说明 | 短路由与调用例子 |
|---|---:|---:|
| 任务正确 | 6/6 | 6/6 |
| 采用 workflow 的任务 | 1/6 | 6/6 |
| workflow 调用 | 1 | 15 |
| 目录查询 | 5 | 0 |
| 引用回读 | 3 | 18 |
| 原生命令 | 31 | 27 |
| 上述原生命令 + MCP 调用合计 | 49 | 60 |
| 输入 token 总计（含缓存输入） | 1,406,183 | 1,448,931 |
| 注入说明 UTF-8 字节 | 8,398 | 2,661 |

配对输入 token 变化中位数 +13.395%，输入总量约 +3.04%。路由提高了采用率，但这组结果未证明效率提升。指导性采用不等于自然发现，更不等于应当所有任务都使用工作流。说明长度与示例同时变化，不能把 token 差异单独归因于工作流。部分试验与本地候选单元测试重叠，墙钟时间不作为因果速度结论。原生系统/模型也有波动，新的原说明组出现 1/6 采用，说明历史 0/40 不是永久失效。

证据：[完整实验](../verification/v06-adoption-probe.json)、[汇总](../verification/v06-adoption-summary.json)、[代表性历史轨迹](../verification/v06-adoption-traces.json)。

## 实际功能缺陷与隔离候选

诊断证据选择匹配 passed 后按日志顺序取前 12 条。在原日志 fixture 中，90 条成功检查挤掉第 93–95 行的全部 3 条 ERROR；真实 Desktop MCP 调用复现错误证据为零。它诚实报告遗漏，但仍迫使模型追加回读。这是已复现的结果质量缺陷，不能倒推为此前模型从未调用它的确定原因。

候选位于同级 codex-ops-adoption-work：
- workflow_diagnostics.py：先选错误/失败/异常，再选警告和成功信息；最后按原行号呈现；优先级依据未裁剪原文。WARN 级别也纳入。保存原日志、遗漏数、部分状态和原行号。
- capability_catalog.py：目录返回四个直接调用配方；SDK 源码按明确 sdk 请求取得。目录响应从 6,579 降为 2,064 字节。
- 4 个新断言在原实现全部失败、在候选全部通过。旧 SDK 目录断言更新为实际跟随 sdk 入口执行，未删除 SDK 验证。
- 全量 358 项测试通过。65 个模块、623 个 Python 函数最大 CRAP=6，超过 6 为零；两个变更模块使用新 statement/branch coverage，其他模块逐个确认源码 hash 相同才复用原覆盖率。没有宣称新测 Rust CRAP 或重新执行全部原生 host 覆盖。
- 同一日志的候选返回第 93–95 行全部 3 条错误；这只是确定性功能验证，尚未证明候选能降低真实模型成本。

证据：[候选验证](../../codex-ops-adoption-work/verification/adoption-repair.json)、[质量](../../codex-ops-adoption-work/verification/quality/crap.json)、[覆盖率来源](../../codex-ops-adoption-work/verification/quality/coverage-provenance.json)。

## 落地顺序

1. 将短场景路由、直接参数示例、轻量目录和错误优先证据合为下一补丁。默认入口不加载整段 SDK，普通调用不需要先查目录。
2. 诊断增加受当前 root 和 native 文件读取约束的日志路径入口；保持已有 log/logRef。文档工作流让足够小的选定证据直接返回，只把完整大结果存为引用，减少先保存再整页取回。不能通过截断失败信息来压低指标。
3. 为 incremental 和 staged task 增加真正有重复读取/阶段依赖/中断恢复的验收，不强迫简单编辑使用复杂计划。
4. 以任务正确率、关键错误保留、原生命令与 MCP 合计、回读次数、总输入量共同验收。采用率只作诊断指标。保持 functions.exec 内完整返回值、原生权限和 CRAP≤6。

本轮生产 Python 源码仍与 0.6.0 发布测量 hash 全部一致。桥接压缩运行中；候选未部署，无需为本轮调查额外重启。
