---
name: compact-output
description: Combine code location, failure diagnosis, document evidence and incremental reads; keep tool output compact with complete retrievable values. Use for verbose logs, staged file changes, ops:// references and compression statistics.
---

Keep complete values inside `functions.exec`; project or aggregate before presenting.
When SessionStart or `ops_stats.runtimeBridge.activeForThisProcess` confirms the
runtime bridge, use ordinary `text(result)` and `notify(result)`. The bridge stores
large emitted text automatically while preserving internal values and native errors.
Without the bridge, pass large values to `ops_capture` and print its receipt.

For multi-step evidence gathering, prefer `ops_workflow` with an absolute `root`:
`locate` combines search and context; `diagnose` accepts `log` or `logRef` and reads
the referenced source locations; `documents` extracts literal evidence from a read
batch; `incremental` compares explicit `files` ranges with an optional `baselineRef`.
The first incremental call returns a snapshot ref; subsequent calls retain exact
current evidence there and report only proven range changes. Read
[workflow contracts](../../docs/workflows.md) for schemas, bounds and examples.
For several programmatic calls, `operation="sdk", args={}` returns a callable
JavaScript factory and argument types. Execute that declaration inside
`functions.exec`, then `createOps(tools, ALL_TOOLS, root)`; it discovers the actual
tool name. Inline receipts are unwrapped; references remain references. Explicitly
call `await ops.resolve(result, maxBytes)` when complete saved data is needed inside
the program (default 64 KiB bound); it never reruns a producer. `runAndDiagnose`
delegates an explicit command to native `exec_command`, retains the full shell value,
and diagnoses completed failures. Running sessions are returned for native polling.
This does not register or replace native tools.

For unfamiliar operations, use `ops_catalog(operation="...")` to obtain the exact
argument schema and a working example. An empty operation returns a thin directory.
For code location followed by reading, prefer `ops_files(operation="search")`:
it combines search with merged context ranges in one request. Check per-stage
coverage and match-change indicators; the two reads are not an atomic snapshot.

Retrieve a saved observation without rerunning its producer:

- `outline` lists child JSON pointers and sizes. Follow a pointer when its structure
  is unknown, instead of retrieving a large body to locate the relevant field.
- `find` searches a literal query across stored strings and returns pointers, line
  numbers and excerpts. Check `scanComplete`; narrow `path` when the scan is bounded.
- `items` selects a decoded JSON pointer, projects `fields`, and literal-filters
  records or lines with `query`. Offset counts matches, returned indices are original.
- `raw` returns exact emitted text or original JSON. Offset counts Unicode characters;
  page size uses `max_bytes`, not `limit`. Follow `nextOffset` to reconstruct all text.
- `count` counts matching stored records; `group` counts by one scalar `fields` entry.
  Check `scanComplete` and `scanTruncatedBy` before treating counts as exhaustive.

Combine 1–8 cached queries with `ops_result(action="batch", requests=[...])`, omitting
the top-level ref. Each request contains its own ref and page options. `max_bytes`
is the entire batch budget; use individual result cursors and errors. Read
[cached queries](references/results.md) for counting, grouping and batch examples.

For items/outline/find/count/group, `limit` is 1–200. Every page uses `max_bytes` 512–16000.
Explicit retrieval pages bypass automatic recapture. A complete saved view does not
prove complete source coverage. Expired references cannot recover discarded bytes.

Use `ops_files` for reads, search, inspection and document extraction under an
explicit absolute root. Batch runs 1–4 independent read-only requests and preserves
their order and individual failures. Read [file arguments](references/files.md)
for request formats and CSV/TSV, DOCX and restricted PDF boundaries.

For a batch of file changes, read [mutation planning and recovery](references/mutations.md).
For dependent changes or explicit directory operations, use `ops_task` after
`ops_catalog(operation="task")`. Plan `args={stages:[[{operation,args}], ...]}`;
inspect its summary before running the returned native argv. Lifecycle actions
`status`, `resume`, `cancel` and `rollback` also return native commands, with
`args={id}`. Cancel is cooperative between steps; use native process control for
an active shell. See [task execution](../../docs/tasks.md).
`ops_plan` checks 1–32 disjoint explicit-file operations and saves a version-checked
plan. Review its summary, then execute the returned `nativeExecution` argv through
Codex's `exec_command` and normal permissions. Planning grants no execution authority.
After an uncertain result, inspect the journal and choose resume or rollback;
do not repeat apply. Ordinary small edits can continue to use native editing tools.

Preserve shell `session_id`, `exit_code` and truncation information. Poll through
native `write_stdin`; a successful-completion hook may capture only the final chunk.
Running/failing/unverifiable direct Bash results retain native output. Outer Code
Mode compression can summarize logs while the program's returned objects stay intact.
Same-frame repeated output can reuse a reference; prior chat history alone never
proves that a repeated file body is still present in the model's current context.

Use `ops_stats(origin="production")` for daily evidence; validation is separate.
Select `window="hour"`, `"day"` or `"week"` for completed five-minute buckets;
the current partial bucket and older unbucketed data are excluded. Inspect collection
coverage before comparing periods. The default `all` retains lifetime-instance totals.
Presentation counters measure emitted UTF-8 bytes. Retrieval costs separately measure
successful result pages, including repeated requests; do not add them twice or call
gross compression token savings. Known tools and session identities are attributed;
Code Mode identities and MCP chat identities are distinct, hashed dimensions.
Unknown and ambiguous sources remain unattributed. For the local interactive HTML
snapshot or explicit loopback refresh service, see [dashboard export](../../docs/dashboard.md).
An optional explicit task root adds bounded journal summaries; these show journal
phases, not a fresh verification of file postconditions. Native CLI status performs that check.

New MCP references with native chat metadata bind to that chat and its available
permission metadata. Automatic output references bind to the native runtime;
Code Mode identities are not chat identities. Runtime restart can make those refs
unavailable. Legacy references retain their original bearer scope. New unattributed
MCP calls bind to the verified runtime or local MCP process; executable reference
plans require native chat identity.
These checks do not isolate hostile processes under the same OS user. References
last up to 24 hours within a 100 MiB logical quota. See
[reference ownership](../../docs/session-scope.md).
Use `ops_result(action="release")` to release a reference when finished.

`ops_stats(check_runtime=true)` distinguishes package/configured/current runtime
versions and verifies staged files. A configured version is not evidence that an
already-running Desktop has loaded it. Native `hooks/list` owns hook trust status.
