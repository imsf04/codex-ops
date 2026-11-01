"""Read-only checks of the configured, installed and actually attached runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import runtime_status
if os.name == 'nt':
    from runtime_bridge import control
else:
    control = None


def _manifest(root):
    return json.loads((root / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))['version']


def _configured_version(override):
    return Path(override).parent.parent.name if override else None


def _bundle(root, version):
    path = control.BASE / 'runtime' / version
    receipt = path / 'bundle.json'
    if not receipt.is_file():
        return {'available': False, 'checked': False}
    data = json.loads(receipt.read_text(encoding='utf-8'))
    bad = [name for name, digest in data['files'].items() if not _matches(path / name, digest)]
    return {'available': True, 'checked': True, 'files': len(data['files']), 'mismatchedFiles': bad,
            'valid': not bad}


def _matches(path, expected):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def _actions(version, configured, active):
    if configured != version:
        return ['Configure the validated runtime with control.py enable.']
    if active.get('runtimeVersion') != version:
        return ['Fully quit and reopen Codex Desktop, then verify this chat again.']
    if not active.get('activeForThisProcess'):
        return ['Validate the current native host before enabling output transformation.']
    return []


def report(check_files=False, root=None):
    root = Path(root) if root else Path(__file__).resolve().parent
    version = _manifest(root)
    if control is None:
        return {'packageVersion': version, 'configuredVersion': None, 'activeRuntimeVersion': None,
                'activeForThisProcess': False, 'restartRequired': False,
                'nextActions': ['Automatic output bridge is not available on this platform.'],
                'hookTrust': 'Use native hooks/list; file existence alone does not establish trust.'}
    override = control.user_environment()['value']
    configured, active = _configured_version(override), runtime_status.current()
    result = {'packageVersion': version, 'configuredVersion': configured,
              'activeRuntimeVersion': active.get('runtimeVersion'),
              'activeForThisProcess': active['activeForThisProcess'],
              'restartRequired': configured == version and active.get('runtimeVersion') != version,
              'nextActions': _actions(version, configured, active),
              'referenceIsolation': {'mcp': 'native chat and available permission metadata',
                  'automaticOutput': 'native runtime; Code Mode IDs are not chat IDs',
                  'legacy05': 'existing bearer references retain original expiry',
                  'localUserBoundary': 'does not isolate hostile processes running as the same OS user'},
              'sdk': 'explicit callable JavaScript helper; no dynamic native tool-registry replacement',
              'hookTrust': 'Use native hooks/list; file existence alone does not establish trust.'}
    if check_files:
        result['stagedBundle'] = _bundle(root, version)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-files', action='store_true')
    args = parser.parse_args()
    print(json.dumps(report(args.check_files), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
