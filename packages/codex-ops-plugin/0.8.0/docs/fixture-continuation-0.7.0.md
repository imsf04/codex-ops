# Explicit LF producer continuation / LF 产出器修订续测

Date: 2026-10-30. This is a fixture correction, not a production behavior fix.
The original task module, native oracle, expected answer, required LF bytes,
acceptance thresholds and production source remain unchanged.

## Proven mismatch / 已证实的问题

The original long_command_failure script called Path.write_text with a string
ending in newline. Native Windows execution produced bytes ending 0d0a, while
the frozen requiredFiles oracle required 0a. Both original and revised scripts
were actually executed via native command/exec under workspace-write, without
any model call. Both exited 7 with the same diagnostic. The revised script uses
write_bytes and its native receipt exactly matches the unchanged expected bytes.

The prior solve_for_self_test path directly wrote expected bytes and therefore
did not exercise this producer defect. The new native producer proof does not
call that helper or fabricate the receipt.

[Native producer proof](../verification/v070-fixture-lf-native-proof.json)

## Scope of correction / 修订范围

tests/v070_fixture_continuation.py calls the frozen prepare_task and, only for
long_command_failure, changes the generated run_probe.py write_text call to
write_bytes. It updates the protected-input hash for that generated script.
The task prompt, expected answer and requiredFiles bytes stay identical.
The explicit revision is receipt-lf1; revised attempt keys carry that suffix.

原来的严格失败保留。新结果不回填旧case的 passed，也不把原尝试成本删除。
修正的是产出器与既有断言不一致，并非放宽断言以让测试通过。

## Composite dataset / 组合数据集

At the graceful stop, the original final report had 28 completed attempts:
26 non-long attempts are retained verbatim with original report SHA/source key;
two invalid-producer long attempts remain in excludedInvalidFixtureAttempts
with their original outcomes and usage.

The independent continuation schedules only 46 new attempts: the remaining
non-long work plus all six long trials (three pairs) using receipt-lf1.
The comparable dataset is 72 rows, with explicit provenance for every row.
It is a multi-cohort composition, not a single unchanged run.

The original two invalid-producer attempts are included in developmentConsumption
but excluded from comparable-pair performance metrics. The earlier stopped first
candidate's separate usage audit must also be included when reporting all project
development consumption. No costs disappear.

Twelve retained rows lack outer observations. Fourteen retained rows have the
earlier observation sidecar. New attempts use the same native raw-event wrapper.
Counts from older unavailable rows are never backfilled with zero.

## Driver and checks / 驱动与检查

tests/run_v070_continuation.py defaults to plan-only. Paid execution requires
--run. It verifies the frozen source/runtime/oracle/acceptance hashes, preserves
whole pairs, refuses overwriting reports, records new source hashes, and checks
that the retained original report remains unchanged. Use a new continuation
stop-file; do not accidentally reuse the still-present final-round stop flag.

Three unit tests verify the isolated adapter, exact 26+46 composition with original
failures preserved, and refusal to retry an in-flight source. Native execution
separately verifies the producer's exit and bytes.

The output is verification/v070-costs-combined.json by default, with
verification/v070-continuation-observation.json as its new observation sidecar.

