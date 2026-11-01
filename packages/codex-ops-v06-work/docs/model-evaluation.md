# 0.6 controlled model evaluation

The suite contains twenty task instances: four each for source location, repair,
batch changes, log diagnosis and document lookup. Two repeats per instance and
three conditions produce 120 scheduled attempts. The actual configured model,
native workspace-write sandbox and ordinary workspace/cache directory layout are
held constant. Native and frozen 0.5 start first; 0.6 starts after staging and source
validation. Actual timestamps are retained because all three groups cannot be fully
interleaved before the candidate exists. Up to two independent app-server processes
run concurrently. This introduces system-load and cache-order effects.

Native has no OPS instructions. Enabled conditions receive their actual skill and
active SessionStart text through native `developerInstructions`, along with their
MCP tools and staged bridge. This tests equivalent guidance, not hook execution.
It does not exercise a genuine DSH host or prove cross-harness superiority.
The entire enabled skill is injected eagerly for every fixture. Daily on-demand
skill loading and actual PostToolUse hook execution are not reproduced; extra
instruction/schema overhead on these small tasks is part of this measured treatment.

Each fixture rejects the unsolved state and accepts an independent expected solution.
The trusted evaluator runs inside the same native sandbox, outside the model-editable
fixture source. Input hashes, exact requested output files, field types and hidden
repair cases are checked. Repair cases reject input mutation and container aliasing.

The original answer oracle was too literal for several unspecified label fields.
Original outcomes are retained, and existing files are re-evaluated without rerunning
the model. The frozen `v06.3-frozen-semantics` interpretation is:

- Source paths accept forward/backward separators and an absolute fixture prefix.
  The actual source/test path and definition/evidence line still must match.
- Authorization `override` accepts `suspended`, `suspension`, `suspended flag`,
  `suspended status` or `suspension overrides ownership`.
- Rounding accepts `half-up`, `half up`, `round half up`, `half-up rounding`, `half_up`.
- Migration cause accepts the actual `SCHEMA_VERSION` code or the equivalent labels
  `schema_version_mismatch` / `schema version mismatch`.
- Trace `downstream` accepts `ORDER_ABORTED` or its actual downstream service `orders`;
  the prompt did not distinguish those interpretations. Other services fail.
- Compiler cause accepts `TS2322` or that exact code followed by a colon and explanation.
  Observed type accepts `string` or `source.age is [the] string "42".` (single quotes
  and a missing final period also accepted). Expected type accepts `number` or the
  description beginning `User.age must be a number, parsed as an integer at the import boundary`.

Other values remain exact, including lexical identifiers, integer/boolean types,
money, source identities and line numbers. A negative test independently corrupts
every requested answer field; wrong path, line, type and error identity must fail.
The source hashes of the final oracle are recorded. Later mismatches are retained,
not solved by adding output-specific aliases or rerunning paid attempts.

Efficiency percentages cover successful, comparable pairs only. Every failed,
timed-out or blocked attempt remains in the suite and success counts. Total/input
tokens include repeated cached context; noncached input is reported separately and
is not represented as a bill. Native completed command/MCP/file-change event counts
are an explicit work-item proxy, not a claim to count every nested JavaScript call.
Twenty correlated task instances do not establish statistical or general superiority.
