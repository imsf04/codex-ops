# Read-only workflows

`ops_workflow(root, operation, args)` combines evidence-producing reads. `root` is an
existing absolute directory. The native file worker still rejects escapes, links,
credential paths and unsupported formats. A workflow never executes a shell command
or grants permission to modify files. Inspect each stage's status and coverage.

| Operation | Arguments | Result |
| --- | --- | --- |
| `locate` | Existing `ops_files(search)` arguments | Matches, merged context ranges and reread revision checks. |
| `diagnose` | Exactly one `log` or `logRef`; optional `maxLocations`, `maxEvidence`, `before`, `after` | Relevant diagnostic lines and one native batch of source ranges. |
| `documents` | `requests:[{operation,args}]`, optional literal `query`, `maxEvidence` | Selected response-string evidence with JSON pointers and exact result references. |
| `incremental` | `files:[{path,offset?,limit?}]`, optional `baselineRef` | Full first windows, then explicit range diffs against the supplied saved snapshot. |
| `sdk` | `{}` | Executable JavaScript client factory and TypeScript declarations. |

Diagnose accepts at most 256 KiB of UTF-8 log text. A saved log must be a string or
a shell object with string `output`; it is an observation, not a new execution.
Bounded JSON-encoded shell envelopes from automatic `text(shellResult)` capture
are decoded before line parsing, including known MCP text wrappers. Arbitrary JSON
with an `output` field but no shell identity is kept as text rather than reclassified.
Python traceback, `file:line`, bare/named Node stack frames, Rust `--> file:line:column`
and TypeScript `file(line,column)` locations are parsed.
At most 16 locations and 40 diagnostic lines are selected, with omission counts.
Locations outside the selected root are counted and never read. Missing or denied
files retain native errors. These heuristics do not prove that all failures were found.

Documents accepts 1–4 native `read`, `read_table`, `read_docx`, `read_pdf` or `inspect`
requests. Their arguments are unchanged; use `ops_catalog` for their schemas. The
literal query visits at most 4,000 nodes per saved response and returns at most 40
400-character excerpts per request. `scanComplete` describes that saved response,
not the original document. `sourceComplete` and `sourceCoverage` retain native
completeness, truncation and continuation, including per-file ranges. Zero matches
with an incomplete source or evidence scan produce `matchConclusion: "unknown"`,
not proof of absence. Follow `resultRef` and the JSON pointer for exact saved content;
use source continuation to read omitted document pages.

Incremental accepts 1–8 ranges of 1–300 lines. Every call reads the current requested
ranges. The baseline must belong to the same trusted session, root and exact range
requests. `snapshotRef` stores the full current native result under `/result`;
`baselineRef` identifies the comparison input. Unchanged lines are omitted only
because the caller explicitly requested a comparison. No model-context retention
is assumed. A changed whole-file revision with no range changes means the selected
window stayed equal; it does not mean the whole file is unchanged. Expired or
inaccessible baselines fail before rereading; begin a fresh baseline explicitly.

For Code Mode, request `sdk` (retrieve its `/javascript` field if it returns a reference),
execute its `createOps` declaration in `functions.exec`,
then use `createOps(tools, ALL_TOOLS, root)`. The factory discovers exactly one
`ops_workflow` name, retaining account prefixes, and calls the real MCP operation.
Calls unwrap inline receipts and preserve large reference receipts without automatic
retrieval. `ops.resolve(result, maxBytes=65536)` explicitly retrieves raw pages and
reconstructs a workflow outcome; it discovers the actual `ops_result` name. The byte
limit is decoded UTF-8 content, 512 bytes to 1 MiB, with a 256-page ceiling. Page
envelopes require budget space, so a remaining budget below 512 bytes rejects further
retrieval. Expired/denied references or insufficient budgets throw; the original
receipt remains available for selective retrieval. Producers never rerun.
The client does not register, hide or replace
host tools. The factory and all four workflows are exercised in the actual native V8
host against the native read worker; this is not evidence of dynamic SDK registration.

```javascript
const ops = createOps(tools, ALL_TOOLS, "C:/project");
const result = await ops.diagnose({logRef: "ops://...", maxLocations: 4});
text(result);
// Only if full evidence is needed:
const full = await ops.resolve(result, 65536);
text(full.diagnostics);
```

The explicit SDK helper `runAndDiagnose(execArgs, diagnosticArgs={})` composes a
caller-supplied native `tools.exec_command` request with diagnosis of a completed
failure. It preserves the complete shell return value inside JavaScript. Running
sessions return immediately for native polling; successful commands are not diagnosed
again. Outputs over 256 KiB are returned with an explicit diagnostic-skipped reason
so the caller can select a bounded log slice. No shell command runs inside MCP, no
command is rewritten or replayed, and native permissions/errors remain native.

```javascript
const run = await ops.runAndDiagnose({cmd: "python -m unittest", yield_time_ms: 1000});
text(run); // Inspect state, shell.session_id, shell.exit_code and optional diagnosis.
```

Large workflow receipts retain bounded diagnostic/document/change evidence; complete
results and native errors remain retrievable. Read omissions before claiming completeness.
