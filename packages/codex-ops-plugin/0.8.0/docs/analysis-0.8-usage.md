# 0.8 usage and cost investigation

Date: 2026-10-30. Chinese: [analysis-0.8-usage.zh-CN.md](analysis-0.8-usage.zh-CN.md).
This is a read-only analysis of existing rollouts and frozen trials. No new model trials or production changes were made.

## What is actually adopted

The desktop restart request was recorded at 02:17:23.301 UTC; the present research turn began at 02:21:39.697 UTC. A snapshot across 39 October rollout files found:

| Cohort | investigate | verify | evidence / working_set | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Explicit restart smoke | 5 | 2 | 0 / 0 | Deliberately invoked acceptance checks |
| Current plugin research | 1 | 0 | 0 / 0 | One selected investigation, not ordinary daily-work evidence |

Of the five smoke investigations, two rejected bad requests (nonexistent path and maxBytes below its documented parser minimum), one returned no match, and two collected source evidence. All seven native MCP items had host status `completed`, illustrating why transport completion is not task success. The two verify calls collected failure evidence. Exact numbers and timestamps are in [the rollout audit](../verification/v080-live-rollout-audit.json).

There is no independently labelled ordinary-task opportunity cohort yet. Daily adoption rate is **unknown**, not 0%, and the current chat's lifetime workflow counter mixes old versions, development, and smoke checks. Native completion counts are not an eligible-opportunity denominator. The snapshot is not a census of remote/nonlocal conversations.

The frozen paid evaluation did not force tool selection, but eagerly supplied the version's skill and simulated SessionStart instructions. It supports selection under that setup, not daily on-demand adoption:

| Across 36 task attempts per condition | 0.6.1 | 0.7.0 |
| --- | ---: | ---: |
| Attempts with any workflow | 23 (63.9%) | 21 (58.3%) |
| investigate calls | 0 | 21 |
| documents calls | 12 | 4 |
| diagnose calls | 3 | 3 |
| evidence / working_set / verify calls | 0 / 0 / 0 | 0 / 0 / 0 |

These percentages are workflow-containing **attempt shares**, not eligible-opportunity adoption rates. New investigate replaced locate/incremental, while the broader workflow footprint did not increase. The suite does not establish that evidence, working_set, and verify were warranted on every attempt. Source: [frozen summary](../verification/v070-cost-summary.json), `workflowUse`.

## The unmet targets and where the gap lives

On 28 common-success pairs, native actions were 197 → 159 (−19.29%, target −25%); input tokens including cache were 5,999,077 → 5,036,759 (−16.04%, target −20%). Uncached input fell 7.07%. Closing the frozen gaps requires at least **12 fewer native actions** and **237,498 fewer input tokens** on the same pair set. These are arithmetic gaps, not promised causal savings.

| Common-success task group | Pairs | Native actions 0.6.1 → 0.7.0 | Input tokens 0.6.1 → 0.7.0 |
| --- | ---: | ---: | ---: |
| Conflicting documents | 3 | 13 → 20 | 400,879 → 675,434 |
| Code location plus regression test | 3 | 14 → 12 | 420,981 → 555,408 |
| Opaque Chinese domain | 3 | 31 → 19 | 959,529 → 553,817 |
| Resume partial work | 3 | 32 → 21 | 979,667 → 660,162 |
| Repair tests/configuration | 3 | 37 → 29 | 956,945 → 822,528 |

The two regressing input groups add 408,982 tokens versus their baselines. Merely matching baseline on conflicting documents would mathematically put the overall input reduction at 20.62%; matching both would put it at 22.86%. Native PowerShell/CWD failures contributed, so these numbers cannot all be credited to an achievable plugin fix. Full task rows: [task deltas](../verification/v080-benchmark-task-deltas.json).

Observed task traces explain concrete friction:

- `1-conflicting_documents-v070`: two failed native file-list calls; documents routed `policy.docx` through plain `read`; a raw retrieval followed, then native ZIP/XML parsing. A typed document route could avoid the wrong decoder, but does not explain the preceding host failures.
- `3-conflicting_documents-v070`: investigation found draft Markdown/CSV but not the approved DOCX. `glob` was called with a string and rejected because it expects an array. Corrected glob, read_docx, an answer read, and another glob followed. One entry point should discover formats and return approved/draft provenance without requiring operation-schema guessing.
- `2-code_location-v070`: the initial anchors `429` and `retry` found implementation and surrounding sources, but no regression test. A native test-directory search failed; a second investigation for `8000` returned `test_backoff.py`. The task asked for implementation **and** regression evidence at the start. Plan coverage across both evidence requirements before spending the result budget.
- A separate resume-partial attempt had a confirmed presentation-induced reread: preview omissions hid successful documents and an ACCESS_DENIED status. Status/error retention still deserves priority over more aggressive shortening.

Sources: [72-trial native tool audit](../verification/v070-combined-tool-audit-final.json), corresponding existing `eventsPath` JSONL files in [the combined report](../verification/v070-costs-combined.json), and [final failure audit](../verification/v070-final-failure-audit.json). Frozen outcomes remain unchanged.

Retrieval calls increased 1 → 3; only one candidate case is confirmed display-induced, others remain causally unknown. Do not claim the reread-reduction target passed. Actual outer-call evidence exists for only 30 of 36 pairs; its common-success subset is 23 pairs, not all 28.

## What timings say about a Rust rewrite

Across the common-success main turns, candidate summed task wall time was 1,704.737 s. Native completion records report 27 workflow calls totalling 15.047 s (median 563 ms), and all plugin tool calls together total 20.325 s, approximately 1.19% of summed task wall time. All recorded native tool durations total 153.797 s, approximately 9.02%. Baseline workflows: 25 calls, 13.935 s, median 415 ms.

These are observed host item durations, **not CPU profiles or an Amdahl speedup bound**: calls can overlap, some actions lack durations, and host duration includes process/transport work. Nevertheless, the evidence does not support a full Python-to-Rust rewrite as the primary route to lower model wall time or tokens. Fewer model round trips, correct routing, and useful first-pass evidence address the measured costs directly. Use Rust selectively after cold-start, serialization, worker-spawn and CPU timings identify a real bottleneck. The original worker is already Rust.

Source: [duration audit with per-call samples](../verification/v080-observed-tool-duration.json). Oracle activity after the main turn is excluded. No speedup claim or language benchmark was fabricated.

## Proposed measurement and product priorities

1. Deliver typed document/code/log routing, schema-correct short recipes, and evidence requirements that include requested tests or authoritative documents.
2. Make compact packets preserve actionable errors and missing evidence, with direct bounded views that prevent a raw-reference retrieval from becoming another clipped reference.
3. Let high-value workflows be selected through task-shaped interfaces; keep low-cost exact reads native. Measure successful evidence delivery and subsequent avoidable reads, not invocation volume alone.
4. Label daily tasks, validation, plugin development, and paid trials separately. Define eligible opportunities for each workflow before claiming an adoption rate; preserve per-version source and model settings. Do not add a model judge merely to generate the denominator.
5. Re-run the frozen cost suite only after targeted document/code/recovery tests show the concrete regressions fixed. Keep cached/uncached input, output, outer calls, native actions, success, and wall time separate.
6. Profile runtime components, then replace a measured hot path with a tested Rust implementation if justified. Preserve failure, exact-observation recovery, authorization, and polling contracts across the boundary.
