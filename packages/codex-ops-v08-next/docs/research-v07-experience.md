# Codex Ops 0.7: design from the agent's actual work

Research date: 2026-10-29. This is a proposal, not an implemented or installed release.
[中文](research-v07-experience.zh-CN.md) · [Primary-source GitHub research](research-v07-github.md)

## Product criterion

Given a question, deliver enough reliable evidence to continue working, without
catalogue lookup, SDK setup, envelope parsing, page-by-page retrieval and manual
reassembly. One useful invocation replacing several steps matters more than high
plugin invocation counts. Automatic presentation, explicit investigation and
native execution should share an evidence engine.

This investigation itself exposed friction: ordinary reads became references,
then required retrieval; a large locate envelope was recaptured. The 0.6.1 small
documents/diagnose fix works, but useful medium-size and other workflow results
still need a unified delivery contract. Raising all thresholds is not sufficient.

## Observed adoption and cost

The audit covers 2026-10-28 15:29:08 through 2026-10-29 15:29:08 Singapore time.
It scans 33 rollouts in two date directories, deduplicates response/call/item IDs,
and follows parent/fork ancestry to separate plugin development and its agents.
This investigation is excluded. Raw conversation bodies are not copied into the report.

| Cohort | Sessions with actions | Native command + MCP + file changes | ops_result | ops_workflow |
| --- | ---: | ---: | ---: | ---: |
| Other work: four independent chats plus their agents | 8 | 851 | 50 | 0 |
| Plugin development/validation plus its agents | 16 | 1,347 | 55 | 4 |
| Other work after 0.6.1 installation | 1 | 273 | 17 | 0 |

An interim count excluded only the plugin parent and included its child agents;
the table corrects that. Eight sessions are not eight eligible workflow tasks.
The audit establishes zero observed natural workflow calls, not an opportunity
adoption rate. Older date directories were not scanned. Installation time alone
does not establish the active runtime of every process.

The post-install business chat received workflow/logPath runtime guidance and
the 0.6.1 skill description. It nevertheless used no workflows. Its 233 commands
were heuristically classified as 108 file reads, 22 searches, 23 test/build,
24 network/remote and 56 other. Compound commands cannot simply be rewritten.
Its 17 retrievals touched 13 references: 16 raw calls and one items projection;
existing batch retrieval was not used.

Across 137 model requests it consumed 19,756,310 input tokens, including
19,574,144 cached and 182,166 uncached input tokens. First/last request inputs
were 27,334/224,550. These are consumption figures without a matched control,
not savings or dollar costs, nor proof that the plugin caused context growth.

The day presentation snapshot records 2,936,239 to 2,188,712 UTF-8 bytes,
a 747,527-byte (25.5%) reduction. It includes development/validation and is not
version-filtered. Retrieval accounting records 292,892 bytes over 50 calls,
including two repeated pages. Bytes do not establish token or billing savings.

The previous 0.6.1 controlled benchmark remains the paired cost evidence:
ten common successful pairs reduced observed actions 24.2% and cumulative input
21.9%; median paired input change was only -3.8%. Both arms passed 11/12 strict
tasks. Failures remain part of the report.

Evidence: [usage audit](../verification/v07-usage-audit.json),
[business detail](../verification/v07-business-detail.json),
[presentation snapshot](../verification/v07-presentation-snapshot.json),
[0.6.1 release evidence](release-0.6.1.md).

## Six proposed directions

1. **Question to evidence, directly.** A discoverable investigation entry needs
   root and question, with optional files/refs. It composes existing location,
   log and document capabilities, without compulsory catalogue/SDK setup.
   Return definitions, callers, overrides, conflicting evidence, source locations
   and unsearched scope. Prefer bounded deterministic retrieval/ranking; do not
   introduce hidden model calls or recursive agents. Native reads remain valid.

2. **Useful content on the first delivery.** Deliver relevant source ranges,
   diagnostic blocks and complete table rows with columns. Give medium useful
   results a relevance-aware shared budget. Recognize bounded explicit retrieval
   and workflow outputs consistently; callers should not unwrap many envelopes.
   Preserve full internal values, media, errors, exit status and session identity.
   Required instruction files must still be read according to their requirements.
   Automatically use existing batch/find/items/count/group where appropriate.

3. **Question-directed retrieval across sources.** Index acquired evidence with
   exact fields/symbols and FTS/BM25. Search multiple references/files/documents
   in one request with provenance, source coverage and contradictory candidates.
   Existing batch retrieval is the foundation, not a newly claimed feature.
   Revalidate ownership, permissions and revisions. Do not add default paid
   summarization or embedding calls without measured benefit.

4. **A complete native verification flow.** Compose native command execution,
   progress, final status, grouped failures, source evidence and a justified next
   check. Read-only MCP must not silently run mutation/test commands. Start with
   deterministic pytest/npm/cargo/git interpretation and retain unknown output.
   Improve CWD/access-error diagnosis and explain transient runtime-status
   disagreement. No privilege changes, blind retries or false successes.

5. **Recoverable task evidence and working set.** Track verified facts, source
   revisions, unresolved questions, completed actions and pending checks.
   Build compact resume packets with targeted invalidation after source changes.
   Existing explicit incremental reads and same-frame dedup are not new features.
   Cross-turn dedup requires actual context-visibility evidence: an unchanged file
   does not prove the model still sees its old body. Without that evidence,
   provide self-contained content or explicit retrieval. Start with provenance,
   invalidation and recovery, then experimentally evaluate cross-turn optimization.

6. **Optimize complete-task cost.** Attribute model requests, outer exec calls,
   native actions, input/cached/uncached/output tokens, latency, failures and
   rework separately. Track eligible/selected/completed/fallback opportunities,
   excluding validation from natural adoption. Adapt evidence budgets when
   immediate rereads show overcompression. Include indexing, retrieval, model
   calls and retry costs. Begin with shadow observation/offline replay.
   Fewer plugin calls can be a success when completed tasks become cheaper.

## Position relative to dsh-ops

Upstream release v0.4.4 and default-branch main differ; independent version
numbers are not capability rankings. Upstream retains advantages in native tool
replacement, dynamic PTC registration, sidebar and cross-platform distribution.
Our existing extensions include automatic Code Mode outer presentation preserving
program values, small inline evidence, composed workflows and ordered dependent
task stages/recovery. These do not establish overall superiority.

Aim to exceed upstream on complete evidence delivery, natural adoption and
measured end-to-end task costs. Do not rebuild functions.exec or optimize tool
counts. Open upstream read-batching/search issues are not shipped features.

## Sequence and acceptance

Deliver directions 1+2+6 first, then 3+4, then the recoverable working set in 5.
Compare every slice against 0.6.1 rather than deferring evaluation until release.

Freeze acceptance before coding. Suggested evaluation: at least twelve task
families with three paired repeats, real directories, access errors, late log
failures, contradictory documents, long-running commands, recovery and agents.
Keep instructions equal and do not explicitly force workflow selection. Retain
all failures; do not relax a perfect-pass gate after observing results.

Ambitious targets, not measured promises: another 25% reduction in common-success
actions, 20% in cumulative input, no uncached-input increase, and half as many
presentation-induced immediate retrievals. Also report all-attempt totals,
medians, per-task results and tails. Small samples cannot prove general quality
equivalence. Keep production CRAP <=6 and require original-value, protocol,
permission and completeness regressions to pass. Validate opportunity adoption
in actual work, not only forced demonstrations.

