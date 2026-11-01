"""Compare 0.5 and 0.6 on actual unittest and Git output, preserving failures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from presentation_policy import Presenter
from reducers import encode
from store import Store


def execute(command, cwd):
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding='utf-8')


def old(raw, cache):
    baseline = Path(os.environ['LOCALAPPDATA']) / 'CodexOps/runtime/0.5.0'
    code = 'import sys;sys.path.insert(0,sys.argv[1]);from presentation_policy import Presenter;print(Presenter().render(sys.stdin.read()),end="")'
    result = subprocess.run([sys.executable, '-c', code, str(baseline)], input=raw,
        capture_output=True, text=True, encoding='utf-8', check=True,
        env={**os.environ, 'CODEX_OPS_STORE': str(cache)})
    return result.stdout


def measure(name, result, base):
    value = {'output': result.stdout + result.stderr, 'exit_code': result.returncode}
    raw = encode(value)
    baseline = old(raw, base / (name + '-old'))
    with patch.dict(os.environ, {'CODEX_OPS_STORE': str(base / (name + '-new'))}):
        displayed = Presenter().render(raw)
        receipt = json.loads(displayed)
        store = Store()
        try:
            recovered = store.get(receipt['ref']) if receipt.get('kind') == 'reference' else displayed
            assert recovered == raw, name
        finally:
            store.close()
    return {'case': name, 'exitCode': result.returncode, 'originalBytes': len(raw.encode()),
        'baseline05Bytes': len(baseline.encode()), 'candidate06Bytes': len(displayed.encode()),
        'rawRoundtripExact': True, 'previewKind': receipt.get('preview', {}).get('kind'),
        'presentation': receipt}


def main():
    with tempfile.TemporaryDirectory(prefix='codex-ops-v06-evidence-') as temporary:
        base = Path(temporary)
        tests = execute([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
            '-p', 'test_v06_presentation.py', '-v'], ROOT)
        assert tests.returncode == 0, tests.stderr
        records = [measure('unittest-success', tests, base)]
        script = 'import unittest\ndef failure():\n assert 3 == 4, "EXPECTED_DIAGNOSTIC ledger mismatch"\ns=unittest.TestSuite([unittest.FunctionTestCase(failure)]);r=unittest.TextTestRunner(verbosity=2).run(s);raise SystemExit(not r.wasSuccessful())'
        failure = execute([sys.executable, '-c', script], base)
        assert failure.returncode == 1 and 'EXPECTED_DIAGNOSTIC' in failure.stderr
        records.append(measure('unittest-failure', failure, base))
        git = base / 'repo'
        git.mkdir()
        assert execute(['git', 'init', '-q', str(git)], base).returncode == 0
        for index in range(80):
            (git / f'module_{index:02}.py').write_text(f'def value_{index}():\n    return {index}\n', encoding='utf-8')
        assert execute(['git', '-c', 'core.autocrlf=false', 'add', '.'], git).returncode == 0
        for name, args in [('git-diff', ['diff', '--cached', '--no-color']), ('git-status', ['status', '--short', '--branch'])]:
            result = execute(['git', *args], git)
            assert result.returncode == 0
            records.append(measure(name, result, base))
        report = {'type': 'actual-command-presentation-comparison', 'baseline': '0.5.0',
            'candidate': '0.6.0', 'externalModelCalls': False, 'cases': records,
            'limitations': ['Actual local unittest/Git commands; no model task-efficiency claim',
                'TypeScript/build/pytest formats have deterministic fixture checks, not installed-tool benchmark evidence',
                'A useful diagnostic preview can be larger than a generic preview; compare evidence retained as well as bytes']}
        path = ROOT / 'verification/v06-evidence-benchmark.json'
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps([{k: v for k, v in row.items() if k != 'presentation'} for row in records]))


if __name__ == '__main__':
    main()
