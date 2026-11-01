# Codex Ops 0.8.0 release verification

[中文](release-0.8.0.zh-CN.md)

Status: final measured candidate; cost and strict quality gates failed. Installed desktop remains 0.7.0. No experimental waiver or installation has occurred.

## Behavior

- Code investigation accepts root plus a question, applies intent-specific source/test/config plans, and invokes one bounded Rust read kernel. The kernel reuses the existing MIT-licensed dsh-ops crates; there is no full-language rewrite or persistent worker.
- Source packets retain exact line provenance and explicit omissions. Model-only views deduplicate paths/revisions while preserving the complete program result and exact raw recovery. Oversized rows cannot starve later fitting implementation/test evidence.
- Document reads select the existing DOCX/PDF/CSV/TSV reader automatically. Partial success, nested per-file errors and unread-source limits remain visible.
- Same-chat/root evidence can be reused after current file revisions are checked. Working-set recovery includes available source content and pending notes without assuming earlier model context remains. Equivalent lexical paths are compared consistently, while native authorization and revision checks remain authoritative.
- Native command output supplies status, exit/session state and diagnostic evidence automatically where applicable. Existing test/build/diff/diagnostic views retain priority. The plugin does not execute a second command or bypass host approvals.
- Cost records distinguish outer model calls, native actions, internal worker starts, cached/uncached input, useful evidence and actual automatic delivery. Validation and production origins are separate when the host forwards the explicit origin; unknown identity is not guessed.

## Deterministic verification

The final frozen Python run passed 543 tests, eight baseline/bridge comparisons and three instrumented shim cases. Its 96 production/installation modules contain 932 measured functions: maximum CRAP 6, zero above 6, combined statement/branch coverage 98.99%. [Python receipt](../verification/quality/crap.md)

The new Rust kernel has 40 measured production functions, maximum CRAP 5.0042867, zero above 6. Measurement uses Lizard complexity and the lower of actual LLVM line/region coverage; stable branch/MC/DC coverage is not claimed. Ten Rust unit tests and eight native Python integration tests passed. Unchanged upstream crates and the existing launcher shim are outside this new Rust-coverage measurement. [Rust receipt](../verification/rust-quality/latest.json)

Fifteen native transport/Code Mode cases passed. A fresh composite binds the final Python source hashes, all 36 staged runtime files and the Rust kernel binary; it verifies a long native failure, polling, direct workflow delivery, changed-file evidence with a new revision, and exact original-value recovery. Earlier case receipts retain their source-specific historical scope. [Current native receipt](../verification/v080-native-friction-current.json)

## Model costs and adoption

**Final gate: FAIL; 0.7 remains installed.** The fresh evaluation completed all 132 attempts. `finalCandidate=true` identifies the measured source; `costGatePassed=false` and `releaseGatePassed=false` prevent promotion. [Final report](../verification/v080-cost-summary.json)

| Common-success comparison | Native actions | Outer calls | Input tokens | Uncached input | MCP worker starts |
|---|---:|---:|---:|---:|---:|
| Against 0.6.1, 31 pairs | −16.19% | −6.80% | −7.44% | −7.79% | +66.67% |
| Against 0.7, 43 pairs | −7.75% | −10.63% | −13.65% | −12.60% | −65.22% |

The required reductions against 0.6.1 remain 25% native actions and 20% input; both were missed. Uncached input improved, but strict quality non-regression also failed. Original pass counts are 33/36 (0.6.1), 45/48 (0.7), and 43/48 (0.8). These include three terminal-wrapper failures per arm. A separately preregistered wrapper correction passed 9/9 supplementary attempts; those results do not replace or merge into the original 132 or its gates. Two candidate late-log answers supplied log text where the fixed oracle required integer line 5001, despite that number being present in the delivered evidence. Both strict failures remain.

Explicit workflow selection is 26/48 (54.17%) for 0.8 versus 22/48 (45.83%) for 0.7. Candidate automatic delivery was observed in 3/48 tasks; the observed union is 29/48 (60.42%). Twelve save-only events are excluded. On the same legacy task set, candidate selection is 19/36 (52.78%) versus 8/36 (22.22%) for 0.6.1. Structural evidence observations are separate from task success. Baseline automatic instrumentation is unavailable, so absence is not zero. These are benchmark observations, not natural daily adoption; production adoption remains unknown.

The remaining costs come from concrete paths: Chinese-only questions can produce `needs_anchor`, domain labels can produce `no_match`, and tools are sometimes discovered in a separate model round despite same-exec guidance. Small tasks already use two calls and little output, leaving little compression benefit; native command batching varies between runs. The inherited diagnostic source-context parser also misreads an entire error prefix as part of a path in all three versions (identical source hashes). That pre-existing bug is separate from the new workflow's English-only automatic-anchor limitation and does not establish the cause of the strict answer-field failures. [Trace audit](../verification/v080-full-provisional-delivery-audit.md), [failure audit](../verification/v080-failure-audit-late-log-2.json)

Pilot, screening, complete-run and supplementary records remain separate. The screening win did not generalize to the full acceptance thresholds. Earlier invalid pilot consumption and failed outcomes are retained. No 0.7 waiver carries forward. A review can choose further optimization, or explicitly waive the failed gates for experimental activation with rollback; neither has been selected or executed here.

## Installation and rollback

`scripts/package_local_plugin.py` defaults to a read-only gate check; `--build` creates the immutable personal descriptor. `tests/install_v080.py --check` performs a read-only preflight; `--install` explicitly promotes the accepted source, installs with the native plugin CLI, verifies installed bytes, trusts the two checked hook definitions through native configuration, then selects the validated runtime.

The existing dedicated production uv environment remains `C:/Users/imsfp/.local/share/codex-runtimes/codex-ops-uv`. Its interpreter, package versions and SQLite FTS5 are checked. The new Rust kernel executable is copied with the accepted live source; Rust build targets and development environments are excluded. Descriptor packaging includes no runtime binaries, raw model traces or private configuration backups.

Before promotion, preserve a 0.7 source ZIP with hashes, previous quality/live receipts, marketplace/config backups and the prior runtime selector. Keep the immutable 0.7 runtime and package cache. `rollback-0.8.0.json` lists the backup and newly added source files. A full rollback restores source and plugin/config state as well as the selector; changing only the selector does not restore the MCP source. Verify current state before restoring backups so unrelated later configuration changes are not overwritten.

Installation records `activeDesktopVerified=false` until a genuine post-restart check confirms the desktop loaded 0.8. A configured selector is not proof of the current process version. No sandbox readiness state is fabricated or security mode changed by the installer.
