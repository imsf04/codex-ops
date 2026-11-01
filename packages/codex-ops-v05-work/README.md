# Codex Ops 0.5.0

Local Codex adaptation of dsh-ops: combine file queries, preserve complete tool
values, present useful evidence and measure retrieval costs. Chinese: [说明](README.zh-CN.md).

## Tools and workflow

| MCP tool | Purpose |
| --- | --- |
| `ops_capture` | Save a large value with a bounded preview; preserve its complete Code Mode value. |
| `ops_result` | Retrieve, locate, count or group saved data; query multiple references without rerunning producers. |
| `ops_files` | Read, search with context, inspect, grep, glob, stat, diff and extract supported documents. |
| `ops_catalog` | List capabilities, then return one selected operation's schema, example and recovery guidance. |
| `ops_plan` | Preflight 1–32 disjoint file changes, save a revision-bound plan and return native execution arguments. |
| `ops_stats` | Inspect the bridge, cache, source attribution, retrieval costs and selected measurement period. |

Use `ops_files(operation="search")` to combine grep and nearby source ranges in
one request. Overlapping ranges are merged; results retain source lines, revisions,
coverage, omissions and continuation. Search and reread are not an atomic snapshot:
matching lines are checked again and reported as unchanged, changed or unavailable.
The two phases share a bounded deadline and never retry automatically.
See [query contracts](skills/compact-output/references/query.md).

Nine native read operations retain the upstream worker's path, credential and
link fences. Independent read batches contain 1–4 requests with ordered individual
outcomes; document extraction supports CSV/TSV, DOCX and restricted text-layer PDF.
See [file arguments](skills/compact-output/references/files.md). For unfamiliar
arguments use [the catalog](skills/compact-output/references/catalog.md): the thin
list is cheap, while an exact selected schema explains shape and bounds. This is
on-demand documentation, not a claim of dynamic native SDK registration.

## Progressive retrieval

`outline` lists child JSON pointers; `find` returns literal matches with pointer,
line and bounded-scan coverage. `items` selects a path, projects fields and filters
records. `count` counts matching saved records; `group` aggregates one scalar field.
`raw` returns exact emitted text or original JSON; its offset counts Unicode
characters and page size uses `max_bytes`, not the row `limit`.

`ops_result(action="batch", requests=[...])` evaluates 1–8 independent cached queries
under one total `max_bytes` budget of 512–16000 bytes. Each query retains its own
result, error, continuation and completeness. A batch performs no source operations.
Follow `nextOffset` and inspect `scanComplete`; saved-view completeness never proves
complete source coverage. Explicit bounded pages and query batches bypass recapture.

## Planned changes through native permissions

`ops_plan` reads and caches a plan without modifying workspace files. Run its
returned `nativeExecution` argv through Codex's native `exec_command`, preserving
actual sandbox and approval decisions. A plan or reference grants no execution
authority, and MCP never starts the mutation executor.

Write, edit, exact-count replace, copy, move and remove use expected revisions,
whole-batch preflight and durable recovery snapshots. Files are limited to 1 MiB,
plans to 8 MiB; parents must exist, paths must be disjoint and transfer destinations
must be absent. A batch is not a cross-file atomic transaction. After uncertainty,
inspect status and explicitly resume or roll back instead of repeating apply.
Journals contain original bytes under `<root>/.codex-ops-mutations/`; recovery
restores content/existence, not all filesystem attributes.
See [mutation contracts](skills/compact-output/references/mutations.md).

## Automatic presentation and context evidence

When `ops_stats.runtimeBridge.activeForThisProcess` is true, ordinary `text(raw)`
and `notify(raw)` use the version-tested Windows bridge. Internal JavaScript values
stay complete; explicit capture remains available without the bridge.

General thresholds remain 2 KiB for structured JSON/shell and 8 KiB for plain
text. Smaller completed-shell outputs are eligible only for recognized semantic
profiles and worthwhile reductions. Successful log summaries, failures and diffs
retain their relevant evidence; source code or documentation is not classified as
a diagnostic merely because it mentions errors. Original emitted text stays retrievable.
Changed terminal state and native diagnostics remain intact. Running-session
repetition and exact repeats within one Execute/Wait response can reuse references.

Cross-model-step read deduplication remains disabled: a transcript, file revision
or window ID does not prove old body text remains in the current model request.
See [context evidence](docs/context-boundaries.md). Direct Bash hooks require a
matching successful-completion record; failures, running chunks and unverifiable
status remain native. Media is unchanged. No executable patch or model/API proxy is installed.

## Measurements, dashboard and storage

Presentation measures emitted UTF-8 bytes by channel, reason, tool and hashed
session identity. Code Mode and MCP chat identities are distinct; unknown or
ambiguous sources remain unattributed. Successful retrieval responses and repeated
page requests are measured separately: they may later be presented, so the two
counters must not be added or subtracted to claim net context savings.

`window="all"` retains instance-lifetime totals. `hour`, `day` and `week` select
completed five-minute buckets; the current partial bucket is excluded. Collection
start, interval and bounded-history loss are explicit; old unbucketed data is not
reconstructed. Recent buckets retain seven days within fixed storage bounds.
Production and validation remain separate; counters contain no commands or bodies.

Export an offline HTML snapshot with `python dashboard.py --output C:/absolute/stats.html`.
Optionally choose `--window hour` and an explicit `--tasks-root` for saved mutation
phases. `--serve` explicitly starts a foreground, read-only loopback service with
manual refresh; it never autostarts. Task phases do not revalidate current files.
See [dashboard instructions](docs/dashboard.md).

Local SQLite observations retain at most 10 MiB each, 100 MiB logically and 24 hours.
Random references are local-user bearer capabilities, not per-chat authorization.
They may contain original tool output; it is not uploaded, encrypted or securely
erased. Release references when finished. Expiry never justifies repeating source effects.

## Installation and verification

Use `codex plugin add codex-ops@personal --json`, review exact hooks through
`/hooks`, and restart Desktop after a runtime update. Update source and version,
not plugin cache. MCP, hooks and the bridge share a dedicated uv environment.
See [deployment/rollback](runtime_bridge/README.md) and [quality](QUALITY.md).

Native protocol tests, real worker cases and fixed tool trajectories check complete
values, bounded output and operational outcomes. Windows sandbox readiness has
been repaired through its native setup flow. The completed real-model pilot used
`gpt-6.1-terra` once per task and condition, without retries: independent checks
passed for **4/5 baseline tasks and 5/5 enabled tasks**. The five tasks cover code
location, test repair, batch changes, log diagnosis and document/table lookup.
See the [paired report](verification/real-model-comparison.json),
[baseline records](verification/real-model-baseline.json) and
[enabled records](verification/real-model-enabled.json).

Only the successful test-repair pair retained comparable workspace layouts and
complete resource records: total tokens fell from **409,938 to 255,490 (37.68%)**,
while elapsed time rose from **72.323 to 154.154 seconds (113.15%)**. Total tokens
include cached input and are not a billing measure. Baseline batch resource metrics
are unavailable. The last three enabled tasks followed a read-only plan-loader fix
and a temporary-directory/cache permission-layout change, so their savings
percentages are withheld. Existing outputs were checked through the same native
workspace-write sandbox after the outside evaluator encountered read denials;
models were not rerun and the original evaluation failures remain recorded.

The enabled condition combined the staged bridge and six MCP tools, without the
plugin skill or SessionStart guidance; only the code-location task used MCP tools.
This small, mixed-configuration pilot does not establish general success-rate,
cost or speed improvements, nor isolate either component's contribution. Run order,
caching, system load and model nondeterminism also affect the measurements.
Current counts are in [the quality report](verification/quality/crap.md).
Output-byte reduction alone does not establish token savings, faster completion or higher task success.

Native plan loading uses a bounded read-only cache snapshot without creating source
SQLite/WAL files. Active writers can make a reference temporarily unavailable before
execution. Metadata-preserving worker publication may exceed Windows workspace-write
permissions; denials and journal state remain visible, with no permission downgrade.
Use an already-permitted native editor when appropriate.
