"""Reproducible quality measurement in the uv development environment only."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main():
    run('-m', 'coverage', 'erase')
    run('-m', 'coverage', 'run', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py')
    run('-m', 'coverage', 'run', 'tests/run_app_server_tests.py')
    reports = []
    for case in ('text', 'runtime_status', 'error'):
        result = subprocess.run([sys.executable, '-m', 'coverage', 'run', 'tests/probe_app_server.py',
                                 '--shim', '--coverage', '--case', case], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', check=True)
        report = json.loads(result.stdout.splitlines()[-1])
        assert report['expectedError'] if case == 'error' else report['rawIntact'], report
        reports.append(report)
        print('PASS instrumented ' + case, flush=True)
    (ROOT / 'verification/quality/instrumented-host.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
    run('-m', 'coverage', 'combine', '--keep')
    run('-m', 'coverage', 'json')
    run('scripts/crap_report.py', '--max-crap', '6')


if __name__ == '__main__':
    main()
