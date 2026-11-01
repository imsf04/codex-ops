# NEXT validation design — no model execution authorized

The current plan is [next_acceptance_plan.v2.json](next_acceptance_plan.v2.json). The earlier unexecuted draft is retained as `next_acceptance_plan.json`; v2 corrects the inherited-skill assumption and selects the established private-home batch route. This document does not authorize setup, paid trials, installation, or promotion.

## Frozen references and candidate scope

Keep `codex-ops-v08-work` and every original report immutable. Its full132 trial remains FAIL. The nine original terminal-status failures, two candidate late-log field failures, and separate9/9 explicit-exit7 supplement remain visible. No result is replaced or regraded.

The next source and isolated runtime are frozen separately. Bind all98 Python source hashes and the `0.8.0-next-1` staged payload hashes. Logical runtimeVersion remains0.8.0, so the launched shim path, manager lineage and actual payload hashes must identify this candidate. Do not enable or overwrite the reviewed canonical0.8 runtime.

Proposed sequence after parent review:

1. **12 candidate screening attempts:** Chinese-domain, late-log, code/test/config holdout and conflicting-documents; all three repeats. Compare matching retained rows, including failures. Screening is not a release gate.
2. **48 new original-protocol candidate attempts:** all16 families×3, because global hook/skill entry changes can affect every task. Reuse the frozen0.6.1/0.7 measurements only after the context-equivalence checks below pass.
3. **3 separate candidate terminal attempts:** the explicit `python run_probe.py; exit $LASTEXITCODE` protocol, compared only with the matching archived supplement. Keep this functional cohort separate from the original main comparison.

Keep the original25% native-action and20% input-token reductions versus0.6.1, uncached-input nonincrease, strict quality nonregression, and CRAP≤6 requirements. Report0.7 incremental results too. Parent review remains necessary; no numerical or quality waiver is implicit.

## Historical pairing is conditional

Reference identity is `(report SHA256, task, repeat, protocol, arm)`, not merely a task name. The plan binds84 main baseline rows, six supplemental baseline rows, original evaluator sources, frozen baseline packages and staged runtimes. Failed rows are included. Prompts, source fixtures, LF receipts, answer fields/types, preservation checks and oracles remain unchanged.

This is **task-matched historical comparison**, not a fresh randomized three-arm experiment or matched random seed. Time, service load and cache warmth differ. Preserve measured total/cached/uncached input; do not refund or normalize tokens to meet a target. Show all-attempt and common-success costs, every baseline-success/candidate-failure pair, and per-family/repeat results. Wall-time differences are descriptive. Missing historical host fields remain unknown.

Before carry-forward, compare the actual native CLI/build, model/effort, effective sandbox/feature/instruction settings, eight tool schemas, on-demand skill catalogue and real hook definitions/execution. Archived catalogues contain **38 skills:37 inherited plus the arm plugin**. Do not remove those inherited skills to make a cleaner-looking experiment. Record relocated absolute paths and any metadata differences. If material context or protocol drift cannot be resolved, historical results are exploratory; do not silently claim equivalent conditions or repeat all84 baselines without a justified plan.

Automatic service was uninstrumented in the old baselines. Compare explicit selection fairly; report candidate observed automatic delivery and task-level union separately. Saved evidence is not served evidence. No evidence-workflow opportunity denominator is invented.

## Native execution route

Use one NEW private authoritative home, `LOCALAPPDATA/CodexOps/acceptance-0.8-next-1/home`, for the whole bounded batch. Reuse immutable baseline sources read-only; install all three native plugin identities in that home and select exactly one per process. Existing opaque API-auth setup may be reused locally without exposing contents. Never copy/link Windows `.sandbox` or `.sandbox-secrets` state.

After explicit parent authorization, perform official Windows setup once for this home. Never provision each arm separately. Verify native execution and catalogue/context equivalence before model calls. Keep all audit/oracle files outside ordinary `C:/Temp` fixture roots.

Setup rotates machine-global sandbox-account credentials. Cleanup therefore belongs to the same operation: close every private host, officially restore the original global home, then verify readiness **and actual native command execution**. Restore after preflight failures, cancellation and trial failures as well. Preserve cleanup receipts. The old review candidate, canonical runtime and live selector remain unchanged.

## Why the global-home shortcut is not yet an acceptance route

Official documentation supports per-process configuration overrides and locates user state under `CODEX_HOME`. Named profiles use separate profile configuration files; they do not create independent Windows sandbox identities. [Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)

The current configuration reference documents skill enablement controls and memory-injection controls. They can help inspect context differences, but changing them is not proof of equivalence to the recorded38-skill catalogue. [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

Installed0.165.0-alpha.1.2 protocol generation and inert tests establish:

- `plugin/install` has no `enabled:false` parameter. The CLI rejects `--profile … plugin marketplace add`. A global install-then-disable sequence is a real global mutation, potentially transiently enabled.
- `thread/start.selectedCapabilityRoots` accepted an external inert plugin and connected its native MCP server/tool with the supplied plugin identity. The first attempt had an obsolete MCP SDK import; that failed receipt is preserved. The corrected MCP2 attempt connected successfully.
- Generic `skills/list` and `hooks/list` did not establish the selected root's per-thread skill/hook behavior. No model turn was sent, no hook trust was granted, and no sandbox setup ran. Thus whole-plugin equivalence is **unproven**, not disproven.

Stop this platform investigation here for this release. Direct-MCP global-home probes can validate payload/native execution, but cannot substitute for whole-plugin discovery/adoption testing. Evidence is retained in `next-profile-write-probe/receipt.json`, `next-capability-root-probe/receipt.json`, and `next-capability-root-probe-mcp2/receipt.json`.

The preparer only hashes/reads references and writes a design JSON under this NEW tests directory. Three focused tests verify failure retention, unchanged full/repeated schedules, and rejection of altered reference bytes.
