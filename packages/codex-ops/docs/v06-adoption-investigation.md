# 0.6.0 activation and workflow adoption investigation

Date: 2026-10-29. Production remains 0.6.0; the isolated candidate is not installed.

## Activation

Desktop manager PID 42800 and native host PID 32464 report 0.6.0. Package, selected and active versions agree. All 29 staged hashes verify, eight MCP tools are discoverable, and both native hooks are enabled/trusted. A 9,731-byte output was automatically captured and recovered as exactly the original 9,569-character string retained inside functions.exec; exit_code=0 remained intact. A real locate call succeeded. The installation receipt now records activeDesktopVerified=true and restartRequired=false.

[Live evidence](../verification/desktop-live-0.6.0.json).

## Historical evidence

The original v06 arm contained 40 tasks. Re-reading every completed item confirms five ops_result calls, three ops_catalog calls and 170 native commands, with no ops_workflow or ops_task. All three workflow catalogue replies were 6,579 bytes, including 3,655 bytes of JavaScript. Subsequent work used native commands. This supports discovery friction as a hypothesis; it does not reveal a unique cause of model choice.

Automatic compression runs at the output bridge. Workflows require model selection, and the SDK is an explicit factory, not native tool-registry integration. Generic args, competing ops_files.search guidance, and a catalogue that leads with SDK source add friction. Small fixtures can already be solved natively. The old suite did not test repeated-range snapshots or staged interruption/recovery, so zero incremental/task use is not a valid failure metric on its own.

## Routing-only experiment

Twelve real gpt-6.1-terra trials: three original fixtures, two repeats, two interleaved conditions. Tools, runtime and user tasks were unchanged. Only developer guidance changed from the full skill/hook to concise scenario routing, direct examples and the same hook. Original instruction hashes match the historical evaluation. All paid trials are retained without retries.

| Metric | Original | Routed |
|---|---:|---:|
| Correct outcomes | 6/6 | 6/6 |
| Tasks using workflow | 1/6 | 6/6 |
| Workflow calls | 1 | 15 |
| Catalogue calls | 5 | 0 |
| Retrieval calls | 3 | 18 |
| Native commands | 31 | 27 |
| Native commands plus MCP calls | 49 | 60 |
| Input tokens including cached input | 1,406,183 | 1,448,931 |
| Guidance UTF-8 bytes | 8,398 | 2,661 |

Median paired input change is +13.395%; total input increased about 3.04%. Guided adoption improved, but efficiency did not. Guidance length and examples both changed; token changes cannot be attributed solely to workflows. Background candidate tests overlapped some trials, so elapsed time is descriptive only. The new original arm used workflows in 1/6 tasks, demonstrating that historical zero adoption is not a deterministic outage.

[Raw experiment](../verification/v06-adoption-probe.json), [summary](../verification/v06-adoption-summary.json), [historical trace sample](../verification/v06-adoption-traces.json).

## Reproduced defect and isolated candidate

Diagnostic selection treated passed lines as evidence and took the first twelve. Ninety successful checks displaced all three ERROR lines 93–95 in the log fixture. The live Desktop MCP reproduced zero returned error lines. Omission was reported, but extra retrieval was necessary. This result-quality defect does not establish why earlier models never selected the workflow.

The sibling codex-ops-adoption-work candidate prioritizes failure evidence, then warnings, then success summaries, preserving original line order and omission counts. Priority uses unclipped text and recognizes WARN. Its catalogue provides four direct recipes and defers SDK source to an explicit sdk call, reducing the catalogue to 2,064 bytes.

All four new regression assertions fail on original code and pass on the candidate. The old catalogue assertion now follows the sdk entry and verifies executable source. All 358 tests pass. Across 65 modules and 623 Python functions, maximum CRAP is 6 and none exceed 6. Changed modules have fresh statement/branch coverage; prior coverage is reused for other modules only after exact source hash verification. No new Rust CRAP or full native-host coverage claim is made. The candidate returns all three error lines in the same fixture; its real-model cost effect remains unmeasured.

[Candidate evidence](../../codex-ops-adoption-work/verification/adoption-repair.json), [quality](../../codex-ops-adoption-work/verification/quality/crap.json), [coverage provenance](../../codex-ops-adoption-work/verification/quality/coverage-provenance.json).

## Next patch

Ship concise routing, direct argument examples, the lightweight catalogue and error-priority evidence together. Then add a root/native-read constrained log-path input and inline small selected document evidence, retaining full large results as references. Keep existing log/logRef contracts. Add fixtures that actually exercise incremental snapshots and dependent/recoverable tasks.

Gate on correctness, preserved failure evidence, combined native/MCP calls, retrieval cost and total input. Adoption is diagnostic, not the optimization target. Preserve original program values, native permissions and CRAP≤6. Production Python source hashes remain unchanged; the current bridge is active and this investigation requires no restart.
