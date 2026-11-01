# Codex Ops 0.6.1 validation

Date: 2026-10-29. This record covers the final source and personal local install candidate.

This patch adds logPath input, direct small document results, matching table rows with columns,
a lightweight catalogue, concise routing, and bounded self-contained workflow display without
a second capture. Runtime discovery now filters stale/stopped ancestry records before choosing
the nearest active bridge. Complete program values, native permissions and reference ownership
rules are preserved.

390 automated tests, eight app-server comparison cases and three instrumented shim checks pass.
All 658 functions across 68 Python production/installation modules have CRAP <=6, with 99.18%
combined statement/branch coverage. Fourteen final staged runtime cases pass. Native fault
injection makes the old lookup reject a valid reference; the corrected lookup reconstructs
52,000 bytes exactly over four pages. The Rust shim is unchanged; no Rust CRAP score is claimed.

The final gpt-6.1-terra comparison contains six distinct fixtures, two repeats per version,
24 paid trials. Both arms share model, ordinary workspace layout, existing workspace-write/
elevated sandbox, explicit workdir guidance and identical field representation requirements.
Source and staged hashes are checked before and after. The earlier 24-trial iteration and
uninstalled bundle remain retained. No failed paid attempt was replaced; permissions were not changed.

| Metric | 0.6.0 | 0.6.1 |
| --- | ---: | ---: |
| Strict output success | 11/12 | 11/12 |
| Observed actions, all attempts | 90 | 66 |
| Cumulative input tokens, including cached | 2,688,977 | 1,992,645 |
| Noncached input tokens | 255,313 | 241,221 |
| Retrieval calls | 1 | 3 |
| Actions, ten common successful pairs | 66 | 50 |
| Input tokens, ten common successful pairs | 1,950,933 | 1,524,499 |

Across common successful pairs, aggregate actions fall 24.2% and cumulative input 21.9%;
median paired input change is -3.8%. Across all attempts, actions fall 26.7%, input 25.9%,
and noncached input 5.5%. These bounded-sample results are not a general speed, price or
per-call guarantee. Actions count commandExecution, MCP and fileChange items; the host does
not separately expose outer functions.exec calls. Median final-request input falls from
24,827 to approximately 21,445; this is not a peak-context measurement.

Each arm failed to create one required JSON artifact. Both failures are retained: native
write_file returned ACCESS_DENIED with effectState=none, with cwd/parent-directory access
problems. The write engine and permissions are unchanged. The new diagnostic workflow returned
the correct evidence. Native error objects and a read-only child-journal audit remain in the
development source verification/v061-final-failure-audit.json. Failed trials are excluded from
common-success costs and were not reclassified through semantic grading in the final round.

The original perfect 12/12 task-output gate remains false. Release acceptance uses complete
changed-contract verification, no sampled completion-count regression, lower all-attempt and
common-success costs, and explicit retention of the native-write limitation. This is not
statistical proof of general model-quality equivalence. Retrieval count did not improve;
all three final 0.6.1 retrievals succeeded, with no REFERENCE_UNAVAILABLE.

[Cost summary](../verification/v061-cost-summary.json). Raw final trials remain at development
source verification/v061-costs-final.json; verification/v061-iteration-history.json retains
the earlier build and corrections. The installed package contains safe summaries and docs,
not configuration backups, raw model traces or a development virtualenv.

Installation uses the existing isolated uv production environment with locked dependencies
and no new dependency. The native plugin and immutable runtime are version 0.6.1. Version
0.6.0 source, receipts and runtime remain available for rollback. A full Desktop quit/reopen
is required before the daily app process can be verified as running 0.6.1.
