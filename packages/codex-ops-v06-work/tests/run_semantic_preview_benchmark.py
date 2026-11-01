"""Compare 0.4 and candidate presentation on actual successful/failing test executions."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from presentation_policy import Presenter
from reducers import encode
from store import Store

RUN = '''import sys,unittest
suite=unittest.defaultTestLoader.discover('tests',pattern='test_observation_architecture.py')
if sys.argv[1]=='failure':
 def expected_failure():
  raise AssertionError('EXPECTED_DIAGNOSTIC: ledger total differs by 7')
 suite.addTest(unittest.FunctionTestCase(expected_failure))
result=unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
'''


def baseline(runtime, raw, storage):
    script = 'import sys;sys.path.insert(0,sys.argv[1]);from presentation_policy import Presenter;print(Presenter().render(sys.stdin.read()),end="")'
    result = subprocess.run([sys.executable, '-c', script, str(runtime)], input=raw, capture_output=True,
                            text=True, encoding='utf-8', check=True,
                            env={**os.environ, 'CODEX_OPS_STORE': str(storage)})
    return result.stdout


def run_case(name, runtime, root):
    run = subprocess.run([sys.executable, '-c', RUN, name], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    expected_exit = 1 if name == 'failure' else 0
    assert run.returncode == expected_exit, run.stderr
    value = {'output': run.stdout + run.stderr, 'exit_code': run.returncode}
    raw = encode(value)
    previous = baseline(runtime, raw, root / (name + '-baseline'))
    with patch.dict(os.environ, {'CODEX_OPS_STORE': str(root / (name + '-candidate'))}):
        displayed = Presenter().render(raw)
        receipt = json.loads(displayed)
        store = Store()
        try:
            assert store.get(receipt['ref']) == raw
        finally:
            store.close()
    assert encode(value) == raw
    assert receipt['metadata']['exit_code'] == expected_exit
    evidence = '\n'.join(row['text'] for row in receipt['preview']['evidence'])
    summary = re.search(r'^Ran \d+ tests? in .+$', value['output'], re.M).group(0)
    assert summary in evidence
    assert ('EXPECTED_DIAGNOSTIC: ledger total differs by 7' in evidence) == (name == 'failure')
    assert ('OK' in evidence) if name == 'success' else ('FAILED (failures=1)' in evidence)
    return {'case': name, 'originalBytes': len(raw.encode()), 'baseline04Bytes': len(previous.encode()),
            'presentedBytes': len(displayed.encode()), 'rawValueIntact': True,
            'fullReferenceReconstruction': True, 'exitCodePreserved': expected_exit,
            'summaryVisibleWithoutRetrieval': summary, 'diagnosticVisibleWithoutRetrieval': name == 'failure'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, default=Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.4.0')
    args = parser.parse_args()
    assert (args.baseline / 'presentation_policy.py').is_file()
    with tempfile.TemporaryDirectory(prefix='codex-ops-semantic-benchmark-') as directory:
        cases = [run_case(name, args.baseline, Path(directory)) for name in ('success', 'failure')]
    report = {'type': 'actual-test-output-presentation-comparison', 'externalModelCalls': False,
              'baselineRuntime': str(args.baseline), 'cases': cases,
              'limitations': ['Bytes are presentation sizes, not model token or task-speed measurements.',
                              'Full retrieval is used only to validate exact reconstruction.',
                              'Actual repository tests run; one additional deliberate failing test exercises diagnostic preservation.']}
    target = ROOT / 'verification/semantic-preview-benchmark.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
