"""Explicit SDK source for a real native-command/diagnosis integration probe."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk_workflow import SOURCE

FIXTURE = '''def broken():
    raise RuntimeError("SDK_DIAGNOSIS_SENTINEL")

if __name__ == "__main__":
    import sys
    import traceback
    try:
        broken()
    except RuntimeError:
        traceback.print_exc()
        sys.exit(7)
'''


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def source(folder, python):
    folder.mkdir(parents=True, exist_ok=False)
    fixture = folder / 'diagnostic_fixture.py'
    fixture.write_text(FIXTURE, encoding='utf-8')
    command = '& ' + quote(python) + ' ' + quote(fixture) + '\nexit $LASTEXITCODE'
    setup = 'const workflowRoot=' + json.dumps(str(folder)) + ';\n'
    setup += 'const diagnosticCommand=' + json.dumps(command) + ';\n'
    return SOURCE + '\n' + setup + '''
let originalShell = null, originalShellJson = null;
const observedTools = {exec_command: async args => {
  originalShell = await tools.exec_command(args);
  originalShellJson = JSON.stringify(originalShell);
  return originalShell;
}};
for (const suffix of ["ops_workflow", "ops_result"]) {
  for (const entry of ALL_TOOLS) {
    if (entry.name === suffix || entry.name.endsWith("__" + suffix)) observedTools[entry.name] = tools[entry.name];
  }
}
const ops = createOps(observedTools, ALL_TOOLS, workflowRoot);
const outcome = await ops.runAndDiagnose({cmd: diagnosticCommand, max_output_tokens: 4000});
if (outcome.state !== "completed" || outcome.shell !== originalShell ||
    JSON.stringify(outcome.shell) !== originalShellJson || outcome.shell.exit_code !== 7 ||
    !outcome.shell.output.includes("Traceback (most recent call last):") ||
    !outcome.shell.output.includes("SDK_DIAGNOSIS_SENTINEL")) throw new Error("RAW_CHANGED");
const diagnosis = await ops.resolve(outcome.diagnosis, 65536);
const sourceLines = (diagnosis.context?.items ?? []).flatMap(file => file.items ?? []);
if (diagnosis.operation !== "diagnose" ||
    !diagnosis.sourceRequests.some(row => row.path.endsWith("diagnostic_fixture.py")) ||
    !sourceLines.some(row => typeof row.text === "string" && row.text.includes('raise RuntimeError("SDK_DIAGNOSIS_SENTINEL")')))
  throw new Error("DIAGNOSIS_CONTEXT_MISSING");
text({exit_code: outcome.shell.exit_code, diagnosticLocations: diagnosis.sourceRequests.length,
      diagnosisStatus: diagnosis.status, rawObjectIdentityPreserved: true});
text("WORKFLOW_NATIVE_DIAGNOSED");
text("RAW_INTACT");
'''
