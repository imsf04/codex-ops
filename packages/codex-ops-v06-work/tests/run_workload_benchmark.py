"""Fixed real-tool trajectories: emitted-byte measurement, not a model/token A/B."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

import files
from presentation_policy import Presenter
from reducers import encode
from store import Store


def read_sources():
    paths = ['packages/codex-ops/store.py', 'packages/codex-ops/hook.py',
             'packages/codex-ops/runtime_bridge/manager.py']
    value = files.run(str(REPO), 'read', {'files': [{'path': name, 'offset': 1, 'limit': 300} for name in paths]})
    assert value['status'] == 'completed' and value['pending'] == 0, value
    assert len(value['items']) == len(paths), value
    expected = ['def capture(', 'def process(', 'def main(']
    for entry, marker in zip(value['items'], expected):
        assert entry['complete'] and entry['revision'], entry
        assert any(marker in line['text'] for line in entry['items']), marker
    return value, {'operation': 'read', 'sourceFiles': paths, 'workerRequests': 1,
                   'assertions': ['all source files complete', 'expected declarations present', 'revision retained']}


def search_then_read():
    source = 'packages/codex-ops/store.py'
    search = files.run(str(REPO), 'grep', {'pattern': 'def (capture|result)',
                       'glob': [source], 'limit': 12, 'lineNumbers': True})
    assert search['status'] == 'completed' and search['scanComplete'], search
    assert len(search['items']) == 2, search
    requests = [{'path': source, 'offset': max(1, item['line'] - 2), 'limit': 9} for item in search['items']]
    snippets = files.run(str(REPO), 'read', {'files': requests})
    assert snippets['status'] == 'partial' and snippets['pending'] == 0, snippets
    assert len(snippets['items']) == 2, snippets
    assert all(entry['nextOffset'] is not None for entry in snippets['items']), snippets
    value = {'status': 'partial', 'effectState': 'none', 'search': search, 'snippets': snippets}
    return value, {'operation': 'grep then bounded read', 'sourceFiles': [source], 'workerRequests': 2,
                   'assertions': ['two expected declarations found', 'scan completeness retained',
                                  'bounded snippets preserve continuation rather than claiming full files']}


def batch_inspection():
    sources = ['packages/codex-ops/store.py', 'packages/codex-ops/README.md']
    requests = [{'operation': 'stat', 'args': {'path': path}} for path in sources]
    value = files.run(str(REPO), 'batch', {'requests': requests})
    assert value['status'] == 'completed' and value['requestResultsComplete'], value
    assert [item['index'] for item in value['items']] == [0, 1], value
    assert all(item['result']['exists'] and item['result']['revision'] for item in value['items']), value
    return value, {'operation': 'batch stat', 'sourceFiles': sources, 'workerRequests': 2,
                   'assertions': ['request ordering retained', 'both real files exist', 'per-file revision retained']}


def run_tests():
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_core.py', '-v']
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                            timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and 'OK' in output and 'Ran ' in output, output
    value = {'exit_code': result.returncode, 'status': 'completed', 'output': output}
    return value, {'operation': 'actual unittest subset', 'sourceFiles': ['packages/codex-ops/tests/test_core.py'],
                   'workerRequests': 0, 'shellProcesses': 1,
                   'assertions': ['real tests executed successfully', 'exit code zero', 'test summary retained']}


def reconstruct(ref, expected):
    store = Store()
    offset, calls, rendered_bytes, parts = 0, 0, 0, []
    try:
        while True:
            page = store.result(ref, view='raw', offset=offset, max_bytes=16000)
            assert page.get('status') != 'error', page
            parts.append(page['text'])
            calls += 1
            rendered_bytes += len(encode(page).encode())
            if page['complete']:
                break
            assert page['nextOffset'] > offset and calls < 100, page
            offset = page['nextOffset']
    finally:
        store.close()
    assert ''.join(parts) == expected, 'Full emitted text did not round-trip'
    return calls, rendered_bytes


def measure(name, operation):
    start = time.perf_counter()
    value, details = operation()
    tool_seconds = time.perf_counter() - start
    original = copy.deepcopy(value)
    emitted = encode(value)
    observations = []
    presenter = Presenter(observer=lambda *event: observations.append(event))
    start = time.perf_counter()
    displayed = presenter.render(emitted)
    presentation_seconds = time.perf_counter() - start
    assert value == original and encode(value) == emitted, 'Original tool structure was changed'
    assert len(observations) == 1, observations
    parsed = json.loads(displayed)
    reference = parsed.get('ref')
    calls, retrieval_bytes = (0, 0)
    if reference:
        calls, retrieval_bytes = reconstruct(reference, emitted)
        assert len(displayed.encode()) < len(emitted.encode())
        for key in ('status', 'effectState', 'complete', 'truncated', 'exit_code'):
            if key in value:
                assert parsed['metadata'][key] == value[key], ('Lost useful state', key, parsed)
    else:
        assert displayed == emitted, 'Unreferenced output was changed'
    if name == 'unit_tests' and reference:
        assert parsed['metadata']['exit_code'] == 0, parsed
    return {'case': name, **details, 'toolSeconds': round(tool_seconds, 6),
            'presentationSeconds': round(presentation_seconds, 6),
            'originalBytes': len(emitted.encode()), 'presentedBytes': len(displayed.encode()),
            'savedBytes': len(emitted.encode()) - len(displayed.encode()), 'reason': observations[0][1],
            'referenceCreated': bool(reference), 'originalStructureUnchanged': True,
            'displayedStatePreserved': True,
            'exactEmittedTextRoundtrip': True, 'validationRetrievalCalls': calls,
            'validationRetrievalBytes': retrieval_bytes, 'fullRetrievalWasValidationOnly': True}


def main():
    with tempfile.TemporaryDirectory(prefix='codex-ops-real-workload-') as temporary:
        with patch.dict(os.environ, {'CODEX_OPS_STORE': temporary, 'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation',
                                    'CODEX_OPS_BRIDGE_STATUS': str(Path(temporary) / 'bridge-status')}):
            cases = [measure(name, operation) for name, operation in
                     [('source_read', read_sources), ('search_then_read', search_then_read),
                      ('batch_inspection', batch_inspection), ('unit_tests', run_tests)]]
    original = sum(row['originalBytes'] for row in cases)
    displayed = sum(row['presentedBytes'] for row in cases)
    report = {'version': json.loads((ROOT / '.codex-plugin/plugin.json').read_text())['version'],
              'type': 'fixed-real-tool-trajectories', 'repository': str(REPO),
              'externalModelCalls': False, 'originalBytes': original, 'presentedBytes': displayed,
              'savedBytes': original - displayed, 'reductionPercent': round(100 * (original - displayed) / original, 2),
              'limitations': ['Fixed tool trajectories, not real-model or task-quality A/B.',
                              'UTF-8 presentation bytes are not token or net context savings.',
                              'Full reference retrieval is performed only to verify exact reconstruction and is reported separately.',
                              'Input files may change between runs; this report describes the source paths at execution time.',
                              'No fabricated repetitive bulk logs are used; native worker metadata is included in emitted bytes.'],
              'cases': cases}
    target = ROOT / 'verification/workload-benchmark.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
