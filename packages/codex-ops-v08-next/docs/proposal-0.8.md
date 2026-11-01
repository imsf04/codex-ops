# Codex Ops 0.8 proposal

Date: 2026-10-30. Research/proposal only: no production code change, reinstall, or new paid model evaluation. Version 0.7.0 remains active. [中文](proposal-0.8.zh-CN.md).

## Decision

Prioritize fewer model round trips and complete first-delivery evidence, with targeted Rust core consolidation. Do not start with a wholesale equivalent Python-to-Rust translation. File/search/document execution already uses the dsh-ops Rust worker. A language change alone does not solve tool selection, missing evidence, host authority, or model token cost.

## Evidence

- Upstream main is pinned at 02 b 1 c 0 c 147025 ae 30 df 977227 cdbfd 68 c 6 f 77 a 2 e, package 0.5.0. Its latest 19 commits relative to the local baseline do not modify native Rust. Codex Ops 0.7 is a separate adapter version. See [upstream comparison and primary sources](research-0.8-upstream-rust.md).
- Post-restart smoke invoked investigate 5 times and verify 2 times. Investigation had 2 rejected requests,1 no-match and 2 collected results. Subsequent use is this research. There is no independently labelled ordinary-task opportunity denominator; daily adoption is unknown.
- In frozen trials, tasks selecting any workflow went 23/36→21/36. Candidate investigate appeared in 21/36. There is no natural selection evidence for evidence/working_set/verify.58.3% is trial task coverage, not eligible-opportunity adoption.
- On 28 common-success pairs: native actions 197→159(-19.29%, target 25%); input 5,999,077→5,036,759(-16.04%, target 20%); uncached input 639,205→594,007. Strict success across all attempts 29/36→34/36. Retain FAIL/UNKNOWN and separate user acceptance.
- Native actions exclude internal worker starts; outer exec is a different measure. None is the count of every system operation.
- Conflicting documents regressed by 7 actions and 274,555 input tokens. Code location saved 2 actions but added 134,427 input tokens. Traces show DOCX routed to text, rereading/unzipping, and relevant tests omitted before another search. Host working-directory failures also contributed.
- The original common-success targets need 12 fewer actions and 237,498 fewer input tokens. Restoring document input merely to baseline would arithmetically exceed 20% overall reduction; this counterfactual locates opportunity, not proven achievable savings.
- [Usage audit](analysis-0.8-usage.md) records cohorts, per-task deltas, traces and limits.

## Direct local measurements

[Microbenchmark](../verification/v08-local-profile.json): current production Python, isolated temporary store,7 serial repetitions including first sample; excludes MCP transport, model latency and cold start.

| Operation | Median | Observation |
| --- | ---: | --- |
| Read 44 lines |26.0 ms| Already Rust worker |
| Investigate one file/anchor |112.1 ms|4 worker starts: grep/read/grep/read |
| Present approximately 61 KB log |6.23 ms| Python presentation/storage path |

[Packet sample](../verification/v08-packet-profile.json):11 selected source lines contain 688 characters; packet 7,986 JSONcharacters; MCP envelope 13,591 characters. Coverage/provenance matter, but repeated paths/revisions/stage descriptions are candidates for normalization. Characters are not tokens and one sample is not representative of every response.

The current focus field is validated and echoed, but does not change search/expansion in investigate.py. Definition/reference/configuration/failure are not yet distinct retrieval plans.

## Six priorities

1. **Deliver decision-ready evidence once.** Keep complete machine data and a concise model view. Normalize per-file source metadata; retain line numbers. Prioritize failures, exit codes, conflicts and missing sources, including mixed success/error document batches. Allocate multi-result display budgets by information importance. Preserve exact values and raw paging.
2. **Select evidence by task intent.** Make focus alter retrieval. Include applicable callers/tests/config for code work. Route DOCX/PDF/tables to their readers and expose conflicting versions. Rank stably, exclude generated artifacts where appropriate and report gaps; avoid simply enlarging every budget.
3. **Remove entry friction.** Keep root+question defaults simple. Expose constraints the model actually needs rather than hide them in generic args. Compare dedicated tools with a discriminated single-entry schema using complete schema/runtime costs. Return usable continuations; leave SDK optional. Keep native execution/approval authority.
4. **Make incremental reuse normal.** Within proven chat/root scope, track acquired evidence, unresolved questions and revisions. Reuse valid evidence, refresh changed sources and search existing references. Never guess that a Code Mode identifier is a chat identifier, restore expired access, or claim to remove host conversation history.
5. **Automatically diagnose observed verification results.** Enrich already-observed native failure/completion output without needing a follow-up verify call. Commands, approvals, cancellation and writes stay native. Do not add an MCP executor that bypasses host approvals. Preserve all original chunks and terminal state.
6. **Consolidate the Rust boundary and measure full costs.** Reuse existing crates for a bounded search+context request; target 4→1 worker starts in the measured single-file case. Existing ops-batch is copy/move/remove journalling, not compound readonly investigation. Move storage/index/presentation only when measured or maintenance benefits justify it. Persistent workers require a cancellation/lifecycle redesign of the EOF/process-exit deadline model. Partition costs by version/chat/task/production-vs-validation and separately count outer calls, native actions, worker starts, cached/uncached tokens, retrievals, failures and wall time.

## Acceptance and delivery

Fix the two observed regressing task families first; retain frozen failures, thresholds and 0.7 rollback. Add held-out code/test, document-conflict and polling/failure tasks. Test actual on-demand discovery rather than only eagerly injected skill text; do not force tool names in prompts. Label eligible opportunities independently and measure first choice, useful evidence and further lookup.

Use common-success pairs for costs and report all attempts/failures too. Lower success is not a token win. Original 25%/20%targets remain relative to 0.6.1; also report 0.8 vs 0.7 incremental changes. Proposed stretch targets are 35%fewer native actions and 30%less input versus 0.6.1, without worse uncached input or failure. These are proposed, not achieved or approved gates.

Rust needs its own coverage/complexity-to-CRAP calculation and≤6 gate. The 797 Python-function result does not cover Rust. Protocol differential, cancellation, failure, pagination and original-value checks precede speed comparisons. Deliver evidence/routing improvements without waiting for a wholesale language migration.

Sources: [upstream research](research-0.8-upstream-rust.md), [usage audit](analysis-0.8-usage.md), [release](release-0.7.0.md), [frozen trials](../verification/v070-costs-combined.json), [live verification](../verification/desktop-live-0.7.0.json), [local timing](../verification/v08-local-profile.json), [packet sample](../verification/v08-packet-profile.json).

