"""Interleaved routing-only experiment; original release evidence stays immutable."""
import hashlib
import json
from pathlib import Path
import tempfile
import time

from run_v06_model_benchmark import configuration, trial

PACKAGE = Path(__file__).resolve().parents[1]
ROUTING = '''Codex Ops provides read-only evidence workflows. Call the tool directly;
no SDK setup or catalogue lookup is needed for these common cases. Discover its
actual name by the suffix ops_workflow in ALL_TOOLS. Use the absolute workspace
directory as root and keep native commands/edits for execution and writing.

Choose by the evidence needed:
- To find code and then inspect matching lines, prefer ops_workflow(root,
  operation="locate", args={pattern:"relevant regex",path:".",before:3,after:8,
  maxMatches:12,maxFiles:4}). This returns matches and source context together.
- After reading a failing log once, prefer operation="diagnose",
  args={log:theOriginalLogText,maxLocations:6,before:3,after:6}. If that text was
  saved as ops://, pass logRef instead. Retain the original command result;
  running commands are polled through native write_stdin.
- For evidence across documents/tables, prefer operation="documents",
  args={requests:[{operation:"read_table",args:{path:"relative.csv"}},
  {operation:"read_docx",args:{path:"relative.docx"}}],query:"literal evidence"}.
  Use 1..4 requests of read/read_table/read_docx/read_pdf/inspect. A read request
  is {operation:"read",args:{files:[{path:"relative.md",offset:1,limit:100}]}}.
  Follow resultRef with ops_result only when the returned evidence is insufficient.
- Recheck previously read exact ranges with operation="incremental",
  args={files:[{path:"relative.py",offset:1,limit:40}],baselineRef:previousRef}.
  Omit baselineRef for the first snapshot; never assume old context survives.

These are preferences for matching tasks, not required tool-count targets.
Use native tools for a single known read, simple edits, unsupported formats, or
when bounded evidence is insufficient. Inspect coverage and errors. A workflow
result may be {kind:"inline",value:...} or a retrievable reference; unwrap inline.
ops_task is for dependent stages or explicit recovery needs; ordinary small
independent edits do not require it. For advanced contracts use ops_catalog;
request operation="sdk" on ops_workflow only for repeated programmatic composition.
'''


def main():
    config = configuration('v06')
    model = json.loads((PACKAGE / 'verification/model-v06-suite.json').read_text())['model']
    root = Path(tempfile.mkdtemp(prefix='codex-ops-adoption-'))
    (root / 'workspaces').mkdir()
    conditions = {'original': config, 'routed': {**config, 'instructions': ROUTING + '\n' + config['hookGuidance']}}
    tasks = ('code_location', 'log_diagnosis', 'document_lookup')
    schedule = []
    for repeat in (1, 2):
        for index, task in enumerate(tasks):
            order = ('original', 'routed') if (index + repeat) % 2 else ('routed', 'original')
            schedule.extend({'key': f'{repeat}-{task}-{condition}', 'task': task,
                             'repeat': repeat, 'condition': condition} for condition in order)
    report = {'experiment': 'routing-only', 'model': model, 'root': str(root),
              'startedAt': time.time(), 'schedule': schedule, 'reports': [],
              'instructions': {name: item['instructions'] for name, item in conditions.items()},
              'instructionSha256': {name: hashlib.sha256(item['instructions'].encode()).hexdigest()
                                    for name, item in conditions.items()},
              'limitations': ['Small three-task probe, not a general performance benchmark.',
                              'Only developer guidance changes; tools/runtime/fixtures remain 0.6.0.',
                              'Guided adoption is not evidence of spontaneous discovery or net benefit.',
                              'Original frozen outcome oracle; no failed paid trial retries.']}
    destination = PACKAGE / 'verification/v06-adoption-probe.json'
    if destination.exists():
        raise FileExistsError('Keep the original experiment; choose a new report path')
    for item in schedule:
        row = trial(root, item, conditions[item['condition']], model, 240)
        report['reports'].append(row)
        report['complete'] = len(report['reports']) == len(schedule)
        destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'key': item['key'], 'status': row.get('turnStatus'),
                          'passed': row['outcome']['passed'], 'tools': row.get('completedMcpTools'),
                          'seconds': row['wallSeconds']}), flush=True)
    print(str(destination), flush=True)


if __name__ == '__main__':
    main()
