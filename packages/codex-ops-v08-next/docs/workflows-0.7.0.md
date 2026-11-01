# 0.7.0 workflow contracts / 工作流接口

Use ops_workflow with an absolute root and one operation. Existing 0.6.1 arguments
remain supported. This page describes implemented candidate interfaces, not measured
cost savings. 请求始终使用绝对 root；旧接口保留。本文不宣称成本验收已通过。

| Operation | Args | Behavior / 行为 |
| --- | --- | --- |
| investigate | question; optional anchors, paths, focus, maxBytes | Bounded discovery/context expansion; exact source evidence, not a semantic answer. 有界查找与扩展，返回原文证据。 |
| evidence | refs (1..8), query; optional limit, maxBytes | SQLite FTS5 lexical query over authorized saved observations. 仅检索仍可授权的已获取资料。 |
| working_set | action=save, sources=[{ref,path?,revision?,label?}], title?, pending? | Save an owned source manifest using existing TTL/store. 保存来源清单与待核验事项。 |
| working_set | action=resume, workingSetRef, maxBytes? | Reauthorize refs and recheck file revisions. Changed/expired evidence is explicit. 重新授权并检查版本。 |
| verify | results=[native command chunks], diagnostic options | Analyze observed execution state/log; never run a command. 只分析已观察到的原生结果。 |

investigate extracts explicit literal anchors or identifiers/path tokens from the
question. English words match lexically; Chinese text can match actual repository
text. Unknown domain terminology returns needs_anchor rather than invented symbols.
focus is auto/definition/references/configuration/failure. Evidence is bounded to
4..24 KiB, default 12 KiB, across the whole packet; continuations name omitted work.

调查优先使用显式锚点或问题中的代码标识符；中文可匹配实际源码/文档中的中文。
缺少有效术语会要求补充锚点，不暗中调用另一个模型翻译或构造调用图。

Evidence packets include items with provenance, coverage and continuations.
Source completeness and selected display completeness differ. Reads are not an
atomic snapshot. An unchanged file does not prove old content remains in the model
context. Working sets restore self-contained evidence; they do not edit history.

证据包区分源扫描范围与展示遗漏；不声称多次读取是原子快照，不推断旧上下文仍可见。
工作集恢复不会重建过期引用的权限，也不会把历史事实自动当作当前事实。

The optional SDK verifyRun calls native exec_command/write_stdin, preserves every
raw result, bounds polling and passes observed chunks to verify. The caller can
continue a still-running session natively. MCP performs no command execution.

ops_stats.taskCosts reads only the native chat's local rollout and deduplicates
authoritative usage. Input, cached input, uncached input, output, outer calls and
native actions are separate. Workflow invocation counts have no eligibility
denominator unless an independent audit labels opportunities; adoptionRate stays null.

同 chat 下首次 raw 补读可形成疑似裁切不足信号；至少4次已展示引用和2次30秒内补读，
才提高调查默认预算4 KiB，最高24 KiB。用户指定 maxBytes 优先。无法关联真实 chat、
存储失败或证据不足时保持默认。此代理信号不等于已测得节省或确认过度裁切。

No new third-party dependency is installed. See [provenance](open-source-0.7.0.md).
