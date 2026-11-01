# Native raw-event observability / 原生外层调用观测

Date: 2026-10-30. Evidence: actual installed CLI-generated schema and two free
deterministic localhost-model native probes. No frozen paid harness, oracle,
production source, installed plugin or current trial control was changed.

## Verified capability / 已验证能力

The installed CLI's generated
verification/native-protocol-schema/v2/ThreadStartParams.json exposes
experimentalRawEvents: boolean. Its description says it opts into raw Responses
API items and is intended for internal use. It is experimental, not a general
stability guarantee.

RawResponseItemCompletedNotification.json contains threadId, turnId and item
(ResponseItem). The actual emitted method is rawResponseItem/completed.
Current ThreadResumeParams and ThreadForkParams schemas do not expose the same
field; do not assume that passing it to resume/fork is supported.

Installed executable:
C:/Users/imsfp/AppData/Local/OpenAI/Codex/bin/0ab0e7a8f3779036/codex.EXE
SHA256: 0c09e45bc76433756eb2d492f6db0ce6f269967e6618f4a6ae73e2fa239694b8

## Why current trial data lacks outer events / 当前缺口

tests/run_model_benchmark.py already initializes experimentalApi=true but its
thread/start params omit experimentalRawEvents. Its receive method only writes
item/completed, turn/completed and thread/tokenUsage/updated to events.jsonl.
Thus both subscription and persistence must change in a future round.

The current final round is frozen and cannot retroactively acquire those missing
events. Its outer exec count remains unavailable; native command/MCP counts must
not be relabelled as total outer calls.

## Native probes / 原生实测

tests/probe_v070_raw_events.py reuses the existing probe_app_server.py entirely.
It reads that file, changes exactly one thread/start argument in memory, executes
the deterministic localhost fixture and asserts the original file bytes did not
change. It does not call a paid model or add a network proxy to production.

| Case | Raw notifications | Outer exec | Outer wait | Output blocks | Exact next-request output matches |
| --- | ---: | ---: | ---: | ---: | ---: |
| text + compression | 7 | 1 | 0 | 2 | 2/2 |
| yield + compression | 9 | 1 | 1 | 3 | 3/3 |

Both retained RAW_INTACT. The raw custom_tool_call_output/function_call_output
output values matched the corresponding call_id output sent in the next local
model request. Raw outputs contained the actual presented ops:// references.

The text case has two output items for one call_id (text/notify). Counting output
items as calls would overcount. The yield case has an exec custom_tool_call and a
wait function_call. The fixture omitted namespace, so both were observed under
their native bare names; future real-model recording must preserve namespace
when present rather than manufacture it.

[Text receipt](../verification/v070-raw-events-probe.json)
[Yield receipt](../verification/v070-raw-events-yield-probe.json)

## Next-round implementation / 下一轮接入路径

1. For a newly started evaluation thread, pass experimentalRawEvents=true in
   thread/start while retaining experimentalApi=true initialization.
2. Save rawResponseItem/completed alongside existing events. Do not remove
   existing native action and usage records.
3. Count custom_tool_call/function_call by scoped (threadId, turnId, call_id);
   retain type and namespace/name. Report exec, wait and native actions separately.
4. Retain every tool-output item associated with its call_id. Several output items
   can belong to one call; do not deduplicate their presentation cost away.
5. Associate presented ops:// references with subsequent actual MCP ops_result
   requests by reference identity. This proves a delivery/retrieval chain, not
   by itself its avoidability.
6. Continue human attribution of task-required exact/full content, unread source
   pagination, new evidence needs and presentation-induced repair. Use actual
   model-visible output, source evidence and task need; unknown stays unknown.
7. Version-test subscription/shape on the installed CLI. If raw events are absent,
   expose unavailable, not zero or a synthetic count.

For controlled validation fixtures, retaining exact tool output can support
causal audits. A daily cost ledger should normally retain IDs, counts, sizes,
hashes and bounded attribution rather than complete user prompts or arbitrary
command payloads. Do not persist all raw message items indiscriminately.

无需自造监听器来推断宿主已经能明确提供的数据。但这个原生开关仍属实验能力，
必须按实际二进制验证。当前付费轮次不改变；后续新轮次同时开启并保存 raw 通知，
才能精确统计外层调用、保留真正模型可见的展示并支持补读归因。

## Observation wrapper for remaining unstarted pairs / 剩余未启动配对的观测包装

A separate tests/run_v070_observed.py now wraps the unchanged frozen Host class
in memory. It adds the thread/start opt-in and appends raw notifications to the
same per-trial events file. It calls the original methods, does not send extra
model/native requests, and leaves the frozen source/oracle/threshold hashes intact.

The sidecar records instrumentation time, wrapper hash, original report hash,
prior completed keys as outer-unavailable, and subsequent scoped outer counts.
Only the first main model turn counts; events after its turn/completed, including
oracle activity, are explicitly excluded. Multiple output items remain associated
with one outer call_id.

The wrapper was exercised through the actual Host with a free localhost model,
both control and observed runs. Model request counts and native completion items
were identical. Initial model input and final tool-output content were identical;
only independently generated top-level Responses item IDs differed.
No content, call_id, tool name or output text was normalized.
[Raw A/B receipt](../verification/v070-observed-wrapper-probe.json)
[Identity-only comparison](../verification/v070-observed-wrapper-equivalence.json)

This does add notification serialization and disk I/O. Do not claim zero
instrumentation overhead or compare wall-time across the instrumentation boundary
as a clean causal estimate. Earlier rows remain unavailable for outer counts.
The independent audit prefers native raw events when recorded and falls back to
matching rollouts only when raw events are absent.


