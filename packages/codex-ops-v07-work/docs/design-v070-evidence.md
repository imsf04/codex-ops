# Codex Ops 0.7 evidence architecture / 证据架构设计

Status: design only, 2026-10-30. Production source and installed 0.6.1 are unchanged.
Scope: the five supporting directions behind question-driven investigation.
现有能力依据本文列出的本机源码；新增接口和边界是建议，尚未实现或验收。

Named modules below describe ownership boundaries, not a requirement to create every
file upfront. Extend existing modules where the responsibility stays cohesive; split
only as implementation size, complexity or testing requires. No generic scheduler,
agent framework, plugin API rewrite or summarization service is proposed.

## Shared contract / 共同契约

Use one bounded evidence packet across investigation, diagnostic, document, retrieval
and verification *presentation*. Preserve the original native/MCP return object in code.
A packet is an explicit projection, not a replacement native tool result.

```json
{
  "kind": "evidence-packet",
  "schemaVersion": 1,
  "status": "completed",
  "operation": "investigate",
  "items": [{
    "id": "local-item-id",
    "kind": "source-range",
    "source": {"ref": "ops://...", "pointer": "/items/0", "path": "src/a.py", "revision": "..."},
    "location": {"lineStart": 40, "lineEnd": 58},
    "content": "exact selected evidence",
    "selection": {"reason": "symbol-match", "query": "load_config"}
  }],
  "coverage": {
    "sourceComplete": false,
    "selectionComplete": true,
    "omitted": 12,
    "reason": "presentation-budget"
  },
  "continuations": [{"operation": "result", "ref": "ops://...", "view": "items", "path": "/items", "offset": 5}],
  "execution": {"effectState": "none"}
}
```

Fields are illustrative. Source/path/revision must come from actual adapter results,
never fabricated from an LLM interpretation. A selected source can be complete while the
overall source scan is incomplete. A summary never claims complete source coverage.
Persist raw source once and refer to it; do not require reference retrieval to understand
the delivered packet. No mandatory extra snapshot reference for every tiny result.

Source identity must retain ownership scope from session_scope.py. The packet is not an
authority token. Local rendering accepts only validated bounded shapes, preserves error
and media envelopes, and performs no extra reads merely because an output includes paths.
Question text and retrieved content are data, not instructions to execute commands.

## 1. Unified delivery / 统一证据呈现

Existing boundary:
- workflow.py dispatches read-only workflow operations.
- workflow_preview.py and query_preview.py create operation-specific previews after capture.
- workflow_inline.py recognizes small documents/diagnose output.
- presentation_policy.py recognizes explicit result pages/batches and avoids recapture;
  explicit retrieval is already allowed up to its bounded limit.
- FramePresenter in frame_dedup.py shares the emitted-frame budget and same-frame dedup.
- sdk_workflow.py still makes callers unpack heterogeneous MCP envelopes.

Change:
1. Add evidence_packet.py as the sole shape validation and projection boundary.
2. Have workflow and retrieval producers build packets from full results; old response
   shapes remain the default until all current callers/tests migrate together.
3. Extend the presentation recognizer for validated packets, including one text MCP
   envelope. Never unwrap error or multimodal responses. Unknown envelopes stay native.
4. Rank candidate blocks *before* clipping: matching source range, failure block,
   table row plus columns. Merge overlapping ranges. Keep metadata once at packet level.
5. Preserve a whole useful block when it fits; if it does not, emit an explicitly partial
   range and an exact continuation. Avoid filling the entire packet with repeated metadata.

Minimum implementation needs no model-based summary. Selection budget is byte-based and
distinct from measured model tokens. Required full instruction reads remain full reads.
General shell thresholds must not be raised globally to hide retrieval loops.

Regression gates:
- Medium locate results and multi-document results are readable without one extra call
  when their selected evidence fits the packet budget.
- Deliberately oversized packets respect shared-frame budgeting.
- Native object identity/value, exit status, session id, media and errors are unchanged.
- A displayed partial range cannot be reported as a complete source.
- Retrieval of original saved data remains byte-exact across Unicode pagination.

## 2. Cross-reference retrieval / 跨引用检索

Existing Store.result supports raw/items/outline/find/count/group, with owner checking.
ops_result batch supports 1–8 requests with one total budget. Reuse these; batch is not
a new feature. Add query-over-sources rather than another manual paging API.

Proposed request:
```json
{"action":"search","sources":[{"ref":"ops://..."}],"query":"first build failure","max_bytes":8000}
```

The investigation workflow can call the same internal retrieval function; callers need
not know whether a candidate is from a file read, document, log or already captured output.
Version one indexes already acquired observations only. A source path never grants
new filesystem access: fresh file evidence goes through files.run.

Implementation modules:
- evidence_index.py: SQLite FTS5 index of bounded chunks, stored outside original blobs.
- evidence_chunks.py: deterministic source-aware chunking (source lines, diagnostics,
  complete table rows with header, document paragraphs); preserve JSON pointers/ranges.
- evidence_search.py: query tokenization, literal/code-symbol boosts, FTS/BM25 ranking,
  source diversity, total byte budget, deterministic tie-breaking.
- store.py: owner-checked load, TTL/quota eviction hooks and source metadata boundary.

Use exact terms and code symbols first. Chinese prose needs documented tokenization;
do not promise general semantic understanding from SQLite tokenization. Literal
identifiers extracted by the requesting model remain useful. No paid embedding or
summary call is needed for the base path. Optional semantic retrieval requires its
own measured benefit and data-handling decision.

Build lazily on first search, not synchronously on every capture. Index limit and quota
must count stored chunk bytes. Expiration/removal must make both original and indexed
text unavailable. Query only authorized source refs; authorize again before returning
text. An index row is not proof that its original source is current or still readable.

If FTS5 is unavailable in the production interpreter, fall back to existing bounded
literal find with an explicit search mode; do not silently claim semantic equivalence.
Report indexed/queried sources, scanned chunks and omission/truncation.

Tests: relevant late diagnostic, duplicated blocks, table header preservation, Unicode
terms, code symbols, nonmatching query, expired source, different chat/policy owner,
quota eviction and deterministic ranking. Include contradictory evidence rather than
testing only happy-path matches.

## 3. Native verification closure / 原生验证闭环

Existing sdk_workflow.runAndDiagnose already calls native exec_command and diagnoses
a finished failed result; running jobs return state=running. progress.py compresses
running-output repetitions. task_api.py only plans or returns native execution argv;
mutations/task_* owns ordered mutation recovery. Keep those separations.

Extend the existing Code Mode client with a bounded verification controller:
- start explicit command using native exec_command with explicit workdir;
- retain full native result/session id;
- poll only through native write_stdin and a caller-approved time/poll bound;
- return progress immediately when the bound is reached, rather than blocking indefinitely;
- on completion, select failure groups and source context through diagnose;
- successful commands return concise exit/test totals plus native result in code;
- no rerun, repair, rollback or permission escalation on failure.

MCP can create/format a verification plan and process already observed results.
MCP cannot launch the command. A returned native plan is not execution authority.
Keep invocation simple through an existing callable client binding; do not add compulsory
catalogue/SDK lookups before every verification. The parent integration must validate
how the client is made available before promising a zero-bootstrap experience.

Use verification state distinct from mutation journals:
planned -> running(session id) -> completed(exit code) or unknown.
A lost native process session becomes unknown, never restarted automatically.
Cancellation is native process control, not a fabricated mutation rollback.

Parser adapters should start with pytest, npm test/build, cargo and git diagnostics,
then retain unrecognized output. CWD/ACCESS_DENIED errors receive actionable path
evidence without changes to native permissions.

Tests: instant success/failure, late error after a long success prefix, Unicode,
running without new output, final status change, cancellation, timeout boundary,
lost native session, native denial and mixed stdout/stderr. No test may hide failure
through retries.

## 4. Recoverable evidence working set / 可恢复证据工作集

Existing workflow_incremental.py compares explicit saved ranges and returns
contextRetentionAssumed=false. frame_dedup.py only deduplicates one outgoing result.
Keep both. A stable file revision does not establish current model-context visibility.

Working set minimum:
- chat/root-scoped task id and a small user/model-supplied task description;
- evidence source refs + source revisions/ranges;
- claims labelled supplied or mechanically verified, not automatically true;
- unresolved questions;
- completed native action receipts;
- next verification steps.

Do not persist arbitrary hidden reasoning or entire conversations. Resume is explicit,
bounded and self-contained: construct current evidence packet plus unresolved state.
The same task id does not authorize reuse in another chat. Session resume may retain
same-chat state; starting a new chat requires explicit export/import through authorized
source reads. Runtime-bound old refs must never be resurrected as chat-scoped refs.

Modules:
- working_set.py: task-state update/read contract and bounds.
- working_set_store.py: scoped local SQLite storage and retention.
- working_set_resume.py: verify source availability/revisions through native adapter,
  mark stale/unavailable facts, then select a bounded self-contained packet.

Prefer references over duplicate source blobs. The initial retention can follow existing
24-hour source expiry; retain only a small stale manifest thereafter if requested.
Don't present old indexed text as current source after expiry or source change.

No cross-model-step suppression in 0.7 unless host evidence proves the original body
is still in the active request. Resume packets yield practical savings without needing
that proof. A summarization DAG/context-engine rewrite is not needed for the initial
implementation.

Tests: process restart, source change, deleted/expired refs, changed policy, unavailable
runtime-bound refs, partially valid working set and explicit import refusal.

## 5. Actual-cost feedback / 实际成本与预算反馈

Existing telemetry.py/telemetry_details.py/telemetry_windows.py already track presentation
bytes, attribution and retrieval. bridge_context.py explicitly distinguishes Code Mode
session ids from chat ids. Reuse the accounting tables; do not join unrelated identifiers
by temporal proximity and call that exact attribution.

Add:
- usage_reader.py: bounded incremental read of authoritative rollout usage records,
  dedup by response_id; fallback token_count handling must distinguish cumulative from
  last-request usage and avoid counting both records twice.
- usage_attribution.py: explicit known session/turn lineage; unavailable mapping -> unknown.
- adoption.py: workflow request/completion/fallback and verified opportunity counters,
  with development/validation excluded from natural adoption.
- evidence_budget.py: deterministic bounded policy using recent same-owner delivery
  and immediate retrieval signals.

Report model requests, outer exec, native command/MCP/file changes separately.
Keep cached input, uncached input, output, bytes and latency distinct. Aggregate input
is not peak context. Monetary savings require actual prices and a baseline, so omit
dollar claims by default.

A retrieval shortly after delivery is a signal of inadequate evidence, not proof:
it can be a legitimate follow-up. Require the same reference/pointer lineage, distinguish
pagination from repeated pages, and label inferred motives. Automatic adjustment can
initially use source type and repeated raw expansion; never reduce required error
evidence. Isolate per chat/agent owner; no global throttle that punishes sibling agents.

Rollout reading is local accounting, not new authority to inspect unrelated chat contents.
Read only known authorized usage fields; persist aggregate identifiers/usage, not message bodies.
When live attribution cannot be proved, leave adaptive policy off for that item and keep
the static budget. Presentation must succeed when accounting is unavailable.

Suggested bounded first policy: fixed baseline plus one larger budget tier after repeated
immediate raw expansion, capped by the same frame limit; lower budget only after measured
redundant repetition. Freeze this policy before evaluation. An open-ended online learner
is unnecessary for 0.7.

Tests: duplicated/inherited rollout events, cumulative resets, multiple agents, absent
turn ids, UTC boundaries, counter rollover, accounting write failure, source pagination,
repeated pages and original-value invariance.

## Delivery sequence / 实施与迁移

A. Freeze common packet and evaluation oracle. Add packet projections + validators,
   share existing retrieve/batch budget behavior, establish usage accounting baseline.
B. Integrate investigation with unified delivery. Test natural routing with identical
   prompts and without naming the plugin. This changes adoption only if actual calls rise.
C. Add lazy authorized indexing and verification orchestration.
D. Add scoped working-set resume and bounded feedback budget.
E. Full Python CRAP gate <=6, native protocol/value/permission tests, paired task costs,
   immutable 0.7 runtime/package build, then installed-host verification.

Feature migration is additive: keep existing ops_result views, workflow operations,
mutation APIs and stored 0.6.1 refs usable under their original ownership/expiry rules.
Do not rewrite the immutable 0.6.1 runtime or reinterpret old records as new authorization.
Index may rebuild from accessible original sources; no destructive source-store migration.
New tables carry schema version and bounded retention.

Success is fewer steps to a correct task outcome. Existing task recovery, batching,
incremental reads and same-frame dedup must not be counted as newly delivered capabilities.
No production edits or installation were performed for this design review.

