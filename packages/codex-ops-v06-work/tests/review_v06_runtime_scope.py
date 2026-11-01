"""Independent candidate shim probes; no installed runtime/profile changes."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from native_cli import native_cli

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = []
    with tempfile.TemporaryDirectory(prefix='codex-ops-v06-review-shim-') as temporary:
        binary = Path(temporary)
        shutil.copy2(ROOT / 'bin/codex-ops-cli.exe', binary / 'codex-ops-cli.exe')
        for name, value in {'real-cli.txt': native_cli(), 'bridge-python.txt': sys.executable,
                            'bridge-script.txt': str(ROOT / 'runtime_bridge/manager.py')}.items():
            (binary / name).write_text(value, encoding='utf-8')
        for case in ('runtime_status', 'retrieval', 'native_scope'):
            command = [sys.executable, str(ROOT / 'tests/probe_app_server.py'),
                '--shim', '--shim-path', str(binary / 'codex-ops-cli.exe'), '--case', case]
            if case == 'native_scope':
                command += ['--sandbox-workspace', str(Path(os.environ['TEMP']) / 'codex-ops-probe-jrmkhnjv')]
            result = subprocess.run(command,
                capture_output=True, text=True, encoding='utf-8', timeout=80)
            if result.returncode:
                raise RuntimeError(result.stderr[-5000:])
            report = json.loads(result.stdout.splitlines()[-1])
            records.append(report)
            print(json.dumps({key: report[key] for key in ('case', 'root', 'rawIntact',
                'rawChanged', 'retrievalPageIntact', 'nativeScopeLoaded', 'managerPid')}), flush=True)
    (ROOT / 'verification/v06-independent-runtime-review.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    assert all(record['rawIntact'] and not record['rawChanged'] for record in records)
    assert records[1]['retrievalPageIntact'], records[1]
    assert records[2]['nativeScopeLoaded'], records[2]


if __name__ == '__main__':
    main()
