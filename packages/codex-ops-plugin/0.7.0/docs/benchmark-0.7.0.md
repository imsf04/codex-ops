# 0.7.0 paired model evaluation / 配对模型验收

Prepared 2026-10-30. The first candidate round was stopped after independent review
found missing direct failure evidence in long verify results. Nine completed trials,
one interrupted trial and all known usage remain in v070-costs.json and
v070-first-usage-audit.json; 62 scheduled trials were never started. The repaired
candidate is evaluated separately in v070-costs-final.json. Initial results are not
substituted into the final comparison or erased from development costs.

## Execution / 执行

From the candidate package directory:

```powershell
..\codex-ops\.venv\Scripts\python.exe tests/run_v070_costs.py
..\codex-ops\.venv\Scripts\python.exe -m unittest discover -s tests -p test_v070_model_tasks.py -v
```

The first command prints the plan and makes no model calls. Only an explicit
`--run` starts 72 real trials: twelve independent tasks, three repeats per arm.
Do not run until both immutable bundles and their source quality receipts exist.

```powershell
..\codex-ops\.venv\Scripts\python.exe tests/run_v070_costs.py --run --model gpt-6.1-terra --effort medium --report verification/v070-costs.json
```

Baseline source: sibling codex-ops, version 0.6.1.
Candidate source: this package, version 0.7.0.
Runtime bundles: LOCALAPPDATA/CodexOps/runtime/{0.6.1,0.7.0}.
Both sources and bundles are verified against their receipts before and after
execution. Evaluation/oracle source and frozen acceptance hashes are also kept.
Same native workspace-write sandbox, approval never, and explicit workdir in
both arms. No readiness update, permission fallback or network task access.

## Task coverage / 任务覆盖

Twelve fixtures differ in source material and required outcome:

1. HTTP retry definition and regression (reused).
2. CLI/environment/default precedence with a historical distractor.
3. Chinese question with a code symbol for job retry limits.
4. Chinese domain question without ASCII anchors, grounded in Chinese docs.
5. Exact middle source line preserving Unicode, escapes and quotes.
6. Approved DOCX policy versus contradictory unapproved draft and CSV order.
7. Error after 5,000 successful log lines with supporting source.
8. Tariff document/table calculation (reused).
9. Read, mutate and re-read current config rather than stale notes.
10. Repair nested configuration copying/deletion behavior (reused).
11. Execute a two-second command that ends with exit 7, preserve diagnostics.
12. Resume genuinely partially completed files and preserve completed work.

The model prompt never names an OPS tool or requires a workflow. Correctness
uses independent exact JSON/files or behavioral repair oracles. Tests verify
unsolved fixtures fail, correct solutions pass, protected inputs remain intact,
wrong scalar types fail, and missing required changes fail. The long-command
task additionally requires a native command-completion event showing exit 7;
a fabricated result file alone is insufficient.

用户任务不强制使用插件。十二题不是把一个题重命名十二次；旧任务仅复用三个，
其余使用不同源码、文档、数据、操作或故障。失败与超时保留，不付费重跑替换结果。

## What these trials cannot establish / 不能替代的验收

`FAMILY_MAPPING` explicitly maps every frozen acceptance family and its limits.
A single-agent model run does not establish multi-agent attribution. Restoring
partially completed files does not establish process-restart/reference recovery.
A source-change task does not force indexing, so index invalidation also needs
its deterministic test. Document questions do not force reference/batch APIs.
Access-denied behavior, exact transport preservation and real stale/permission
boundaries require separate native regression gates.

The no-anchor Chinese fixture contains the domain phrase in documentation.
It does not prove semantic understanding of absent vocabulary; deterministic
needs_anchor behavior is tested separately.

## Measurement and acceptance / 测量和判定

Report every attempted run, raw events/stderr/workspace, cumulative input,
cached/uncached input, output, native command/MCP/file actions and elapsed time.
Keep all-attempt totals and common-success pairs separate; show paired median,
per-task values, p50/p95 wall time and baseline-success/candidate-failure pairs.
Token usage missing from a failed attempt is counted explicitly as missing.

Fixed quantitative targets remain 25% fewer common-success actions, 20% fewer
input tokens and no uncached-input increase. The display-induced immediate
retrieval target requires causally labelled evidence; total retrieval calls
are not substituted. Its status remains UNKNOWN in this harness.

`releaseGatePassed` is deliberately false: this report alone cannot validate
protocol, quality, multi-agent and causally labelled retrieval gates. Overall
release assessment must combine their independent receipts without silently
relaxing the frozen acceptance. Incomplete/ineligible samples keep target
statuses UNKNOWN.

The two arms receive their actual skill and SessionStart guidance eagerly as
developer instructions. This measures the version's routing plus code changes;
it is not a claim of identical on-demand desktop skill loading. The same explicit
model and effort are used in both arms. Requests are sequential, paired and
interleaved. There is no automatic failed-attempt replacement or overwritten
existing report.

验收数字不直接代表账单金额；宿主没有可靠提供外层 functions.exec 计数，
因此原生动作口径独立报告。完整日常自然采用和多 agent 仍须另做实测。

