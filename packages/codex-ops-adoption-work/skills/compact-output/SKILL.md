---
name: compact-output
description: Find code with context, diagnose log files, and combine document evidence with compact, retrievable results. Use for multi-step reads, verbose output, ops:// references and staged file changes.
---

Keep full tool values inside functions.exec. With the active runtime bridge, use
ordinary text()/notify(); output compression is automatic. Set native exec_command
workdir to the explicit workspace. Preserve exit_code/session_id; poll natively.

Use a workflow when it combines evidence that the task needs. Call ops_workflow
directly with an absolute root; SDK setup and catalogue lookup are optional.

- Find code and nearby context: operation="locate",
  args={pattern:"relevant regex",path:".",before:3,after:8,maxMatches:12,maxFiles:4}.
  maxFiles is 1..8. Start with one focused search; follow only missing evidence.
- Diagnose a log file: operation="diagnose", args={logPath:"build.log"}.
  Already-read text or an ops:// log can use log or logRef instead; choose exactly
  one. Returned line numbers belong to the original log; inspect scan coverage.
- Related documents/tables: operation="documents", args={requests:[
  {operation:"read_table",args:{path:"prices.csv",limit:1000}},
  {operation:"read_docx",args:{path:"policy.docx"}}],query:"literal key"}.
  Use 1..4 requests. Read text with
  {operation:"read",args:{files:[{path:"notes.md",offset:1,limit:100}]}}.
  Small results are in result; matching table rows include columns. Use them
  directly. resultRef is for missing evidence, not a required second step.
  Check page/scan coverage; a query does not search unread source pages.
- Recheck exact ranges: operation="incremental",
  args={files:[{path:"app.py",offset:1,limit:40}],baselineRef:previousSnapshotRef}.
  Omit baselineRef on the first call. Old chat context is not a saved baseline.

Retain the MCP response in code; when displaying a single JSON text response,
decode it and unwrap only kind="inline". Preserve error and multimodal envelopes.
Do not print a double-encoded content/text envelope just to retrieve it again.
For saved observations use ops_result with a selected path/query; view="raw" and
nextOffset reconstruct exact emitted text. Never rerun a producer to recover it.

Use native tools for a single known read, writing, simple edits and command
execution. Do not introduce workflow calls merely to verify a tiny result already
available in code. For dependent file stages or recovery use ops_task;
ops_catalog(operation="task") provides native execution commands and bounds.
ops_catalog(operation="workflows") gives direct recipes. Request workflow
operation="sdk",args={} only for repeated programmatic composition.

[Advanced contracts](references/advanced.md) cover file operations, staged
mutations, ownership, statistics, dashboard, SDK and complete retrieval contracts.
