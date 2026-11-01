# Codex Ops 0.7.0 candidate validation

Date: 2026-10-30. Implementation and validation are complete. The user explicitly
accepted local activation with unmet cost targets retained and a 0.6.1 rollback.
releaseGatePassed remains false; experimentalAcceptance records this decision
separately without regrading any FAIL or UNKNOWN.
[Full Chinese report](release-0.7.0.zh-CN.md).

Implemented: bounded question-to-source investigation; direct known evidence packets;
authorized cross-reference SQLite FTS5 queries; native SDK verification/polling;
scoped, revision-checked working-set save/resume; actual chat usage accounting and a
bounded reread-driven budget recommendation. No third-party code was copied and no
dependency was added. SQLite FTS5 was exercised in both existing Python environments.
See [provenance](open-source-0.7.0.md) and [contracts](workflows-0.7.0.md).

Full quality checks passed 459 tests, eight app-server comparisons and three
instrumented shim cases. All 797 functions in 83 Python production/installation
modules have CRAP <=6; combined statement/branch coverage is 99.25%.
This does not extend Python CRAP to Rust or embedded JavaScript.
Fifteen staged native cases passed. The strengthened failure test preserved 20,863
characters, executed once, polled once, exposed exitCode=2 and the error directly,
and recovered observations exactly over seven pages. The earlier ACL failure
remains recorded; changing fixture authority did not fix that native limitation.

The comparison uses gpt-6.1-terra / medium, twelve tasks and three repeats per arm.
Both actual version skills and SessionStart guidance were eagerly injected;
task prompts did not force a tool, but this is not ordinary on-demand skill loading.

| Metric | 0.6.1 | 0.7.0 |
| --- | ---: | ---: |
| Strict success | 29/36 | 34/36 |
| All-attempt native actions | 273 | 205 |
| All-attempt input tokens, including cache | 8,187,681 | 6,326,924 |
| All-attempt uncached input | 831,393 | 740,748 |
| 28 common-success pairs: native actions | 197 | 159 |
| Common-success input | 5,999,077 | 5,036,759 |
| Common-success uncached input | 639,205 | 594,007 |

All-attempt actions/input/uncached input fell 24.91%/22.73%/10.90%.
The frozen common-success targets did not pass: actions fell 19.29% against 25%,
and input fell 16.04% against 20%. Uncached-input nonincrease passed.
Display-induced immediate retrieval reduction remains UNKNOWN.

After a no-paid-model native protocol proof, raw event observation was enabled only
for unstarted pairs. Thirty observed pairs had 285 to 214 outer exec calls (-24.91%);
23 common-success observed pairs had 207 to 166 (-19.81%). The first twelve trials
remain unavailable, not zero. Oracle activity is excluded. Native-action counts do
not include internal MCP worker starts, and are not all system execution operations.

Tasks using workflows fell from 23/36 to 21/36. Candidate operations were investigate
21, documents 4 and diagnose 3. The remaining new operations were exercised in
deterministic/native tests, not naturally selected by these model tasks.
No eligible-opportunity denominator exists; no general adoption rate is claimed.
One candidate reread is confirmed to follow a partial documents preview hiding
existing file states/ACCESS_DENIED. Two others and the baseline reread remain
causally unresolved. Total retrievals are not substituted for display-induced rereads.

All nine strict failures were audited. The two candidate long-task failures involved
requested/actual working-directory disagreement or missing required native terminal
exit evidence; neither used the SDK/workflow. One pair passed baseline and failed
candidate. This neither proves a plugin regression nor general quality equivalence.
Native workdir/PowerShell/sandbox root cause remains unresolved; permissions were
not changed and failures were not regraded.

Lineage is explicit: the first candidate stopped for missing verify failure evidence,
retaining nine completed trials and one interruption. The next evaluation exposed
a fixture write_text CRLF producer conflicting with its frozen LF byte contract.
A real native probe proved the mismatch. Only a separate producer adapter changed
to write_bytes, with its protected hash updated; expected answers/oracle/thresholds
did not change. The old two FAILs remain in development costs. The final 72 records
combine 26 retained non-long rows and 46 continuation rows, each with provenance,
rather than pretending to be a single unchanged run.

Known development consumption is at least 16,594,497 input / 16,690,480 total tokens,
including invalid producer trials and last-known interrupted usage. Unreported
in-flight usage remains unknown. These are not dollar charges.

Deployment preserves a 0.6.1 rollback and selects the staged 0.7.0 bundle; Desktop
needs a restart. The installation receipt records actual activation state.
Evidence: [cost summary and acceptance](../verification/v070-cost-summary.json),
[native cases](../verification/v070-native-final-summary.json),
[quality](../verification/quality/crap.json),
[failure audit](../verification/v070-final-failure-audit.json),
[tool audit](../verification/v070-combined-tool-audit-final.json),
[frozen acceptance](../verification/v070-acceptance-design.json).

