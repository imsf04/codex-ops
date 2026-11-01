# 0.7 investigation entry: executable design and read-only exploration

Date: 2026-10-30. Status: design plus existing-adapter exploration, not an
implemented natural-language investigation engine. No production source,
runtime, installed package, permissions or dependencies changed.

## Decision / 决策

The plugin supplies cited evidence, not a claimed semantic answer. The host model
already understands the user's question and can provide domain anchors without
another model call. Make question+root the ordinary interface, with optional
anchors/paths for opaque domain language. A question without useful repository
anchors returns a concise need-anchor result; it must not invent translations,
a call graph, configuration precedence or an answer.

用户的“一个问题换来证据”可以成立，但它依赖调用模型与确定性检索器的分工：
模型负责问题含义与必要术语，插件负责可靠、廉价、完整性明确的证据组合。
不要把当前小样本人工选 seed 的成功包装成自然语言解析已完成。

## Input contract

Proposed operation: ops_workflow(operation="investigate", root, args).
Keep the existing discoverable MCP identity initially; separately test whether
a direct investigation tool improves unguided routing before adding a new tool.

Required args: question (nonempty, <=2000 characters).
Optional: anchors (<=8 exact symbols/phrases), paths (<=8 root-relative paths),
focus ("definition"|"references"|"configuration"|"failure"|"auto").
Default shared evidence budget 12 KiB, bounded 4..24 KiB; one bounded discovery
stage and at most one expansion stage. No arbitrary script/command input.
A future index receives the same validated query, not a separate policy bypass.

Anchor precedence:
1. Explicit anchors are literal strings, escaped before regex construction.
2. Backticked identifiers, path-looking tokens and source-style symbols in
   question (CODEX_CLI_PATH, _fresh, nextOffset) become exact candidates.
3. English lexical terms can rank observed filenames/docs/code terms.
4. Chinese questions with ASCII identifiers work through those identifiers.
   Chinese text can match actual Chinese repository documentation literally.
   A Chinese domain phrase absent from repository text is not automatically
   translated into a guessed symbol. Return need-anchor plus observed candidate
   filenames/terms if a bounded discovery scan has produced them.
5. Questions with no actionable seeds must not fall back to scanning everything
   with an empty regex or silently widening root.

No hidden LLM call, synonym service, embedding service or recursive agent.

## Output contract

Return a single evidence packet with:
- operationStatus: completed/partial/error (execution state).
- evidenceState: candidates/needs_anchor/no_matches (never an inferred answerability score).
- question and interpretedQuery (literal anchors, scopes, expansion rationale).
- evidence[]: source path/revision, exact line range/content, role and selection reason.
- relations[] only for mechanically observed relationships, e.g. same identifier
  text at two locations, or definition and containing module. A textual occurrence
  is not proof of a call edge or effective configuration precedence.
- coverage: searches/ranges attempted, unread scope, scan completion, omitted
  ranges, changed/unavailable matches, budget/deadline reached.
- next: zero or one concise operation proposal carrying exact arguments.

Errors, permissions, changed files and incomplete scans remain explicit.
A completed operation only means its bounded work completed.
Packet content is self-contained under its shared budget; omitted material stays
retrievable. Do not capture an already bounded investigation packet a second time.
An implementation may wrap the packet using the established MCP transport, but
callers should not need to distinguish several result envelope shapes.

## Reuse and module boundaries

workflow.py dispatches investigate into a small workflow_investigate module.
Do not overload query_workflow.options with natural-language policy.

- investigation_query: validate question/anchors; lexical extraction; escaped literals.
- investigation_plan: select bounded stage and one warranted expansion.
- investigation_evidence: normalize native result rows into the shared packet.
- Existing files.run owns native execution, root checks and credential/link fences.
- Existing query_workflow owns grep + context, merged ranges and changed-match checks.
- Shared evidence presentation owns final budget and no-recapture contract.

These are proposed responsibilities; split only where complexity warrants it.
Avoid a general planner DSL or a second executor. Keep production functions CRAP<=6
with behavioral tests for selection/coverage, rather than tests mirroring helpers.

For known Python source, definitions can eventually be expanded to exact function
bounds using syntax over already-authorized content. Other languages need their
own proven parser or a clearly labeled textual range. Never label regex matches
as an AST or a complete dependency graph.

## Three actual project questions / 三个真实问题

All six workflow calls used the installed 0.6.1 locate operation through the
native read adapter. Both seed and expansion scope were selected manually by
the researching agent. This proves useful primitive composition, not automatic
question planning or task-level cost improvement.

| Question | Seed evidence | Expansion observation |
| --- | --- | --- |
| CODEX_CLI_PATH 在哪里设置，如何选中运行版本？ | runtime_bridge/control.py:21 identifies NAME | Definition/DESTINATION expansion finds environment access and enable at lines 31,40,148; result is partial because broad constant occurrences consume the search page. |
| 为什么 ops_result 的 raw 分页能精确还原，nextOffset 怎么计算？ | store.py:111-112 continuation, retrieval_views.py:115 another page path | store.py:148-156 contains actual raw implementation and unicode-codepoints metadata; completed scan and unchanged matches. Initial nextOffset seed alone selected a non-raw view too. |
| 运行时记录过期后，_fresh 如何影响祖先进程选择？ | runtime_status.py:59,69,85 | Expanded definitions at lines 59,65,75 establish freshness predicate, lineage filtering and selection; completed scan and unchanged matches. |

The first seed hit is a constant followed by packaging metadata, not enough
evidence for the user's full question. This is why simply hiding locate behind
a question parameter would be insufficient.

Two expansion responses became stored references before presentation and needed
raw retrieval; the third stayed inline. This reproduces the delivery friction
that the shared evidence packet must solve. No source operation was rerun merely
to recover the stored result.

Detailed receipt:
[design-v070-investigate-probe.json](../verification/design-v070-investigate-probe.json).

## Acceptance / 验收

Freeze tests before implementation:
- Literal punctuation cannot become regex injection; root and credential policy unchanged.
- Chinese with explicit symbol, English phrasing, Chinese-only matching docs,
  and opaque Chinese domain language without anchors.
- Duplicate names, definition vs call-site ambiguity, two conflicting configs,
  late matches, changed source between search/read, denied source and deadline.
- Initial hit lacks definition: bounded expansion retrieves it or labels missing evidence.
- Large bounded packet stays directly usable; full program/MCP values remain intact.
- No-match/need-anchor response contains a targeted next argument, not a verbose manual.

Later unguided model evaluation should compare this operation with 0.6.1 on
identical tasks, without requiring the model to choose it. Count underlying
worker operations and model round trips separately. A single MCP call that
hides more scans is not automatically cheaper. Keep failed tasks and retrieval
costs in the totals.

## What remains unverified

Automatic intent/anchor extraction, autonomous expansion, packet no-recapture,
natural adoption and token reduction are not implemented or measured here.
The first test's partial result is retained. No claim of universal natural-language
code understanding, complete call graph, semantic answer generation or superiority
to dsh-ops follows from these three exploratory questions.

