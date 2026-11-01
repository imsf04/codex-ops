# Codex Ops 0.4.0

Local Codex adaptation of dsh-ops: automatic presentation, progressive retrieval,
native file reads, planned changes and measured retrieval costs.
Chinese: [说明](README.zh-CN.md).

## Tools and workflow

| MCP tool | Purpose |
| --- | --- |
| `ops_capture` | Save large values with a bounded preview; keep the complete value inside Code Mode. |
| `ops_result` | Retrieve `items` or exact `raw` pages, inspect `outline`, locate text with `find`, or release a reference. |
| `ops_files` | Read, inspect, grep, glob, stat, diff, CSV/TSV, DOCX and restricted text-layer PDF; concurrent read-only batches. |
| `ops_plan` | Preflight 1–32 disjoint file changes and save a revision-bound plan; return native execution arguments. |
| `ops_stats` | Inspect cache, current bridge, emitted bytes, source attribution and separate retrieval costs. |

One short skill guides selection; [file contracts](skills/compact-output/references/files.md)
describe arguments and format limits. Read batches contain 1–4 requests and preserve order,
errors, coverage and continuation. File/search previews retain useful records, source
paths, revisions and coverage facts; samples never imply complete reads.

`ops_result(view="outline")` shows child JSON pointers; `find` locates a literal
query with pointer/line context and reports its bounded scan coverage. `items`
supports path selection, fields and literal filtering. Follow `nextOffset`;
`complete` describes the saved view, not the source. Explicit bounded retrieval
pages bypass automatic compaction. Raw offsets count Unicode characters;
`max_bytes` bounds the page and the row `limit` does not constrain raw text.

## Planned changes through native permissions

`ops_plan` reads and caches a plan without modifying workspace files. Its
`nativeExecution` contains the interpreter and CLI arguments to run through
Codex's native `exec_command`; planning or possessing a reference grants no
execution permission. MCP never starts the mutation executor. The native shell
retains sandbox and approval decisions.

Supported operations: write, edit, exact-count replace, copy, move and remove.
Files are limited to 1 MiB and plans to 8 MiB; parents must exist, source/target
paths must be disjoint, and copy/move destinations must be absent. Execution
preflights the batch, records recovery snapshots, and uses the unchanged native
worker with expected-revision checks. A batch is not a cross-file atomic transaction.

After failure/interruption, inspect `status`, then explicitly `resume` or
`rollback`; do not repeat `apply` blindly. Recovery refuses unexpected external
changes. Journals remain under `<root>/.codex-ops-mutations/` and contain original
file bytes. Recovery restores content/existence, not every filesystem attribute.
See [mutation contracts](skills/compact-output/references/mutations.md).

## Automatic presentation and context evidence

The version-tested Windows bridge handles recognized outbound text, notify and
Execute/Wait results. Use ordinary `text(raw)` when
`ops_stats.runtimeBridge.activeForThisProcess` is true. Internal JavaScript
values stay complete; `ops_capture` remains available without the bridge.
Structured JSON/shell output is eligible from 2 KiB, plain text from 8 KiB.
Changed terminal state and error diagnostics are preserved. Repeated running
session output can use a compact reference from 256 bytes; every replacement
must be shorter and its saved text remains retrievable.

Exact repeats can reuse a reference only inside one outgoing Execute/Wait result
frame. No cross-prompt file-read deduplication is enabled: transcripts, file
revisions and window IDs do not prove a prior body remains in the current prompt.
See [context evidence](docs/context-boundaries.md).

Direct MCP hooks can replace presentation without changing nested Promise values.
Automatic Bash hooks compact successful completion only after a bounded native
transcript match; failures, running chunks and unverifiable status pass through.
Receipts distinguish a whole execution from its final polled chunk. The bridge can
compact verbose failure logs while preserving native error state and diagnostics.
Media remains unchanged. No executable patch, model/API proxy or global output-budget change is installed.

## Measurements, dashboard and storage

`presentationTotals` persists emitted UTF-8 byte counts by channel, reason, tool
and hashed session identity, separating production from validation. Code Mode
identities are not chat IDs; verified MCP metadata may supply a distinct chat
identity. Unknown notification sessions and legacy data remain unattributed.
Conflicting producers of the same cached reference remain unattributed.

Successful retrieval response bytes and repeated bounded-page requests are
accounted separately from emitted presentation bytes. They can overlap after
presentation and must not be added/subtracted to claim net context savings.
Observation-link accounting uses daily instance buckets. Inactive instances expire
after 30 days, with at most 128 retained per origin; active aggregates are not an
exact rolling 30-day time series. Counters store no commands or output bodies.
Export a sortable, filterable offline HTML snapshot:
`python dashboard.py --output C:/absolute/stats.html --origin production`. See [instructions](docs/dashboard.md).

Observations use local SQLite under `%LOCALAPPDATA%/CodexOps`: 10 MiB per value,
100 MiB logical quota and 24-hour retention checked on use. Random references
are local-user bearer capabilities, not per-chat authorization; they may contain
sensitive tool output. They are not uploaded, encrypted or securely erased.
Use `ops_result(action="release")` to release them. Expiry never justifies repeating
source effects; saved completeness does not restore host truncation.

## Installation and verification

Use `codex plugin add codex-ops@personal --json`, review exact hook definitions
through `/hooks`, and restart Desktop after a runtime update. Edit source and bump
the version before reinstalling; do not edit plugin cache. Absolute paths target
this machine. MCP, hooks and the bridge share a dedicated uv environment with
locked dependencies; measurement tools stay in the development environment.
See [runtime deployment/rollback](runtime_bridge/README.md) and [quality](QUALITY.md).

Native protocol tests use the installed Codex 0.165.0-alpha.1.2 with isolated
temporary profiles and a deterministic local response server. Fixed real-tool
workloads measure bytes and exact-value preservation. The separate opt-in paired
real-model repair pilot is prepared; no result is claimed until its report exists.
Use the current [quality report](verification/quality/crap.md) and receipts for counts.
Byte reductions alone do not establish token savings, task-quality gains or faster completion.
