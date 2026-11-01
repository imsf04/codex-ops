"""Stage an isolated test label without selecting it or changing production control."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import winreg

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def controller():
    spec = importlib.util.spec_from_file_location('next_test_control', ROOT / 'runtime_bridge/control.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def destination(control, label):
    if not re.fullmatch(r'0\.8\.0-next-[1-9][0-9]*', label):
        raise ValueError('Use an isolated 0.8.0-next-N test label')
    base = control.BASE / 'runtime'
    target = base / label
    assert target.resolve().parent == base.resolve()
    assert target.resolve() != control.DESTINATION.resolve()
    return target


def selected():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
        return winreg.QueryValueEx(key, 'CODEX_CLI_PATH')[0]


def canonical_files(path):
    assert path.is_dir()
    return {str(item.relative_to(path)): sha(item) for item in path.rglob('*') if item.is_file()}


def home_inputs():
    home = Path.home() / '.codex'
    return {name: sha(home / name) for name in ('config.toml', 'auth.json') if (home / name).is_file()}


def active(label):
    command = ("@(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and "
               "($_.ExecutablePath -like '*runtime*" + label + "*' -or $_.CommandLine -like '*runtime*" + label + "*') } "
               "| Select-Object ProcessId,Name) | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], check=True,
                            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(result.stdout) if result.stdout.strip() else []


def import_proof(target, python):
    code = ('import sys,json,importlib,tomllib;from pathlib import Path;root=Path(sys.argv[1]);'
            'sys.path[:0]=[str(root/"runtime_bridge"),str(root)];'
            'names=["manager","workflow_view","diagnostic_view","log_contract","runtime_status"];'
            'modules={name:Path(importlib.import_module(name).__file__).resolve() for name in names};'
            'assert all(path.is_relative_to(root.resolve()) for path in modules.values());'
            'print(json.dumps({"logicalVersion":tomllib.loads((root/"pyproject.toml").read_text())["project"]["version"],'
            '"modules":{name:str(path) for name,path in modules.items()},"paidModelCalls":0}))')
    result = subprocess.run([python, '-I', '-B', '-c', code, str(target)], check=True,
                            capture_output=True, text=True, encoding='utf-8')
    return json.loads(result.stdout)


def stage(control, label):
    target = destination(control, label)
    assert not target.exists(), 'Existing label is immutable; use a fresh label'
    canonical = control.DESTINATION
    baseline = canonical_files(canonical)
    before = selected()
    assert Path(before).samefile(control.BASE / 'runtime/0.7.0/bin/codex-ops-cli.exe')
    credentials = home_inputs()
    assert not active(label), 'An active labelled runtime prevents staging'
    quality = json.loads((ROOT / 'verification/quality/crap.json').read_text(encoding='utf-8'))
    assert {name: sha(ROOT / name) for name in quality['sourceSha256']} == quality['sourceSha256']
    try:
        control.DESTINATION = target
        staged = control.stage()
    finally:
        control.DESTINATION = canonical
    bundle = json.loads((target / 'bundle.json').read_text(encoding='utf-8'))
    assert len(bundle['files']) == 38
    assert {name: sha(target / name) for name in bundle['files']} == bundle['files']
    for name, digest in bundle['files'].items():
        assert sha(ROOT / ('bin/codex-ops-cli.exe' if name == 'bin/codex.exe' else name)) == digest
    assert Path(bundle['settings']['bridge-script.txt']).samefile(target / 'runtime_bridge/manager.py')
    for name, value in bundle['settings'].items():
        assert (target / 'bin' / name).read_text(encoding='utf-8').strip() == value
    proof = import_proof(target, bundle['settings']['bridge-python.txt'])
    assert proof['logicalVersion'] == '0.8.0'
    assert selected() == before and canonical_files(canonical) == baseline and home_inputs() == credentials
    receipt = {'version': '0.8.0', 'label': label, 'staged': str(target), 'stage': staged,
               'sourceSha256': quality['sourceSha256'], 'qualitySourceMatches': True, 'files': bundle['files'],
               'settings': bundle['settings'], 'offlineImportProof': proof, 'canonicalRuntime': str(canonical),
               'canonicalFilesSha256': baseline, 'canonicalRuntimeUnchanged': True, 'selectorUnchanged': True,
               'selectedOverride': before, 'configAuthUnchanged': True, 'nativeExecutionTested': False,
               'limitations': 'Logical version is 0.8.0, so active version alone cannot distinguish labels. '
               'Native validation must bind explicit launched shim path, manager process lineage and these hashes. '
               'Never run the labelled control.py enable/rollback: its normal DESTINATION recomputes canonical 0.8.0. '
               'Promotion requires identical payload hashes plus fresh native smoke at the canonical path.'}
    output = ROOT / 'verification' / ('v080-runtime-' + label.removeprefix('0.8.0-') + '-stage.json')
    output.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return {'receipt': str(output), 'files': len(bundle['files']), 'staged': str(target),
            'logicalVersion': proof['logicalVersion'], 'selectorUnchanged': True, 'canonicalRuntimeUnchanged': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='0.8.0-next-1')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    control = controller()
    prepared = {'preparedOnly': True, 'destination': str(destination(control, args.label)),
                'logicalVersion': control.VERSION, 'payloadFiles': len(control.FILES) + 1,
                'canonicalRuntime': str(control.DESTINATION)}
    print(json.dumps(stage(control, args.label) if args.execute else prepared))
