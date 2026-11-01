# Codex Ops 0.8 native cost/adoption acceptance

Fresh 0.6.1 / 0.7.0 / 0.8.0 comparison; historical 0.7 failures retain their original result. [中文](benchmark-0.8.0.zh-CN.md).

## Conditions

[acceptance-v080.json](../verification/acceptance-v080.json) fixes 12 legacy tasks × three arms × three repeats plus four new task families × two arms × three repeats: 132 attempts. Prompts do not name or require OPS tools. Legacy oracles are unchanged; the documented receipt-lf1 producer revision remains explicit.

Each arm uses its actual staged runtime, native-installed plugin, trusted exact hooks and native skill catalogue. Full SKILL content is not injected eagerly. Actual hook execution and skill reads are recorded separately; trust alone does not prove execution.

One private authoritative CODEX_HOME serves all arms because Windows sandbox accounts are machine-global. Per-process flags enable exactly one arm. Sources, runtimes and per-attempt stores remain separate. No per-arm sandbox provisioning occurs during trials. The release owner restores the desktop's own official sandbox state after acceptance.

Synthetic fixtures use C:/Temp/CodexOpsAcceptance-v080. Authentication, RPC/schema logs, raw events, expected answers, stores and evaluation sources stay outside the searched workspace. Every trial checks that native startup leaves fixture inventory unchanged. [Isolation proof](../verification/v080-workspace-isolation.json) checks actual PowerShell cwd and real Rust search against an audit/oracle marker. This is input/search isolation, not a claim that workspace-write denies every external read.

## Measurements

- Raw native events measure outer model tool calls; completed native items measure command/MCP/file actions separately.
- A transparent observer counts actual MCP server child worker starts, with exact catalogue/result equivalence checked against direct execution. Workers launched by native mutation CLI commands outside this boundary remain unmeasured. Missing observation is not zero.
- Input, cached input, uncached input and output remain separate. Byte compression is not a token-savings or price model.
- Task eligibility is fixed from requirements before trials, including applicable old locate/incremental routes. Report selection, first observed native tool, structural evidence and strict task success separately.
- Automatic saves make evidence available; they do not mean evidence served the task. Only actual reuse or an actually delivered verification preview counts as automatic service. Unlabelled production counts cannot establish daily adoption percentages.

Common-success pairs are the primary cost cohort. All attempts, failures, measurement gaps and baseline-success/candidate-failure pairs remain visible. Missing native/model measurements make the cost gate UNKNOWN.

## Gates

Fresh 0.8 versus 0.6.1 requires at least 25% fewer native actions and 20% less input, non-increasing uncached input and no lower success count. Also report the 0.7 comparison with quality non-regression and non-increasing uncached input. The 35% / 30% values are non-blocking stretch targets. Cost gates do not independently approve release; CRAP, native protocol, installation and failure review remain separate.

The pilot has ten attempts: code_location and conflicting_documents across three arms, plus changed-resume and terminal-failure across 0.7/0.8, one repeat. It validates measurement and representative behavior, not the full release gate. Each new paid round archives evaluation sources and source/config/runtime fingerprints before execution. Failed/in-flight attempts are never replaced.

Pilot 1 stopped after two attempts and is invalid for acceptance. [The invalidation receipt](../verification/v080-pilot-1-invalidation.json) preserves outcomes and known consumption. It also exposed genuine packet-selection weaknesses addressed under a separate candidate freeze. A corrected round has a distinct report, run root and fingerprint.

## Running

Use tests/run_v080_costs.py with --run, --pilot, --configs, --report, --run-root, --workspace-root and --stop-file after release-owner confirmation of fresh validation. Private audit roots and ordinary fixture roots are separate arguments. The full 132-attempt round uses a new report/root without --pilot.

Serial execution is the default. Optional two/three-worker execution uses separate processes, never threads sharing temporary CODEX_HOME changes. A stop file prevents new submissions while retaining active work. Resume cannot rerun an in-flight attempt or change source, profile, schedule, model, effort or concurrency.

