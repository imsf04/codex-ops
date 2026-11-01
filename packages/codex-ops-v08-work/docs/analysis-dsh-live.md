# DSH / dsh-ops real local usage audit

Date: 2026-10-30. Read-only existing-log investigation; no DSH task execution, configuration change or upgrade. [中文](analysis-dsh-live.zh-CN.md).

## Sources and installation

Read all 120 session.v4.jsonl.zstd files beneath C:/Users/imsfp/.dsh/sessions with Python 3.14's standard compression.zstd/json libraries. All parsed. 114 sessions contain tool calls; 106 show OPS use (93.0% session coverage). Active event timestamps span October 17 evening through October 30 at 02:14 Singapore time. This is not eligible-opportunity adoption.

The current desktop node_modules/dsh-ops/package.json reports 0.3.0. Current cordis.yml enables shell/file and disables dsh-ops-ptc/background. No dsh-ops package exists at the checked headless node_modules path. Current state does not version-stamp historical sessions. This is not evidence of the full upstream 0.5.0 feature set or a controlled comparison with Codex Ops 0.7.

## Observed use

Outer calls: 20,690, including 19,460 run_code. Internal PTC dispatches: 32,765. These are different layers, not additive model round trips.

Across the two layers, OPS-named calls total 13,681: ops_bash 13,114; ops_grep 267; ops_replace 128; ops_inspect_local_file 109; ops_glob 63. Shell accounts for 95.9%. PTC also uses native read 6,578 times, edit 5,129, write 2,763 and pwsh 1,471. These native file calls are not OPS SDK calls. Initial presets are 107 PTC and seven standard, but presets can change. Publication/replacement affects tool choice; high coverage is not voluntary preference among equally visible alternatives.

Representative actual work:

| Session | Outer calls | PTC dispatches | OPS evidence |
| --- | ---: | ---: | --- |
| Rhino db1bcfbf… |194 run_code|232|154 ops_bash|
| RPU 18964351… |312|0|309 ops calls, including 230 ops_bash|
| Tutorial/slides a73fe82d… |73 run_code|151|48 ops_bash|

Default workspace does not automatically mean plugin development. See the [chain audit](research-dsh-real-chains.md) for exact source paths and sequence identifiers.

Rhino seq614 combines read/edit/ops_bash in one run_code, returning at seq621. Seq606/609/610 takes native job_output content of 49,931 characters and prints status plus the last 800, yielding 810 characters. This is PTC code projection, not a dsh-ops compression measurement. An OPS shell example (seq939/941/942) slices 49,932 characters to 6,000, but the search included generated coverage/minified JSON; truncation does not establish relevance.

There are practical failures: Rhino seq251/254/258 requested roughly nine minutes of waiting but hit a 120-second host timeout and polled again. Slides seq376/382/383 had exitCode 1 with isError=false, then printed stderr without an explicit exit code; later code fixes saved successfully. Business-command failure is different from plugin failure.

## Usage and pruning

21,062 assistant usage records all satisfy inputTokens + cacheReadTokens + cacheWriteTokens + outputTokens = totalTokens. Their cumulative values are inputTokens 44,799,098; cacheReadTokens 3,706,313,344; outputTokens 19,877,293; cacheWriteTokens zero. Here inputTokens excludes cache reads; do not compare that field directly with Codex's cache-inclusive input. These are repeated request usage totals across sessions, not context size or savings.

There are 872 compaction/prune events, summing 3,745,374 shadowedTokenCount, and 872 replacement tool/result records sharing call IDs. Do not add historical result versions as simultaneously visible bytes. Host pruning is not automatically a dsh-ops saving, nor a measured net token/billing reduction.

Outer call and PTC subcall IDs are unique; assistant message IDs are unique both within and across sessions. No matched plugin-disabled baseline, task-success labels or complete historical version records exist in this audit, so it cannot establish net savings, task success rate or a speed advantage over Codex Ops.

## Implications

Prefer familiar native-facing entry points, clear defaults and native authority. Compose dependent tools within Code Mode while preserving complete program values; deliver concise results with explicit status/exit/error. Select useful source evidence and exclude irrelevant generated artifacts before truncating output. Track host history pruning separately from presentation compression. These logs establish heavy OPS shell usage, not adoption of disabled SDK components or every advanced workflow.

Evidence: [aggregate](../verification/dsh-real-usage.json), [summary](../verification/dsh-real-usage-summary.json), [event identity check](../verification/dsh-event-identity.json), [chain audit](research-dsh-real-chains.md).

