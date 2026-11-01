---
name: compact-output
description: Keep large tool results out of context while preserving raw values. Use for verbose logs, large MCP responses, batch file operations, ops:// retrieval, and compression statistics.
---

Keep complete values inside `functions.exec`; project or aggregate before presenting.
When SessionStart or `ops_stats.runtimeBridge.activeForThisProcess` confirms the
runtime bridge, use ordinary `text(result)` and `notify(result)`. The bridge stores
large emitted text automatically while preserving internal values and native errors.
Without the bridge, pass large values to `ops_capture` and print its receipt.

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

References are local bearer capabilities under the current OS user, retained up to
24 hours within a 100 MiB logical quota. They are not per-chat access controls.
Use `ops_result(action="release")` to release a reference when finished.
