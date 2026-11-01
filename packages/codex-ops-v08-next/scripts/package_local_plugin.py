"""Check or build the local descriptor from a fully accepted frozen candidate."""
import argparse
import json
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE / 'tests'))
from release_v080 import VERSION, digest, require, validate


def build():
    target = SOURCE.parent / 'codex-ops-plugin' / VERSION
    require(not target.exists(), 'Keep the immutable package; inspect before rebuilding')
    target.mkdir(parents=True)
    for name in ('.codex-plugin', 'hooks', 'skills', 'docs'):
        shutil.copytree(SOURCE / name, target / name)
    for name in ('.mcp.json', 'LICENSE', 'README.md', 'README.zh-CN.md', 'QUALITY.md'):
        shutil.copy2(SOURCE / name, target / name)
    for name in ('quality/crap.md', 'rust-quality/latest.json', 'v080-cost-summary.json'):
        destination = target / 'verification' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / 'verification' / name, destination)
    files = {path.relative_to(target).as_posix(): digest(path) for path in target.rglob('*') if path.is_file()}
    require(not any(part in name.split('/') for name in files for part in ('.venv', '__pycache__', 'target')),
            'Runtime/build artifact leaked into descriptor')
    record = {'version': VERSION, 'package': str(target), 'files': files,
              'bytes': sum((target / name).stat().st_size for name in files),
              'runtime': 'Dedicated production uv; validated Rust kernel and Python source promoted separately',
              'excluded': ['development venv', 'runtime binaries', 'private configuration backups', 'raw benchmark traces']}
    (SOURCE / ('verification/plugin-package-' + VERSION + '.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
    return {'package': str(target), 'files': len(files), 'bytes': record['bytes']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', action='store_true', help='Build only after all final release gates pass')
    args = parser.parse_args()
    try:
        validate(SOURCE)
        result = build() if args.build else {'ready': True, 'version': VERSION, 'mutations': False}
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'ready': False, 'reason': str(exc)}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
