"""Freeze measured sources, actual descriptors and successful private preflights."""
import hashlib
import argparse
import json
import os
from pathlib import Path
from preflight_v080_profiles import profile as native_profile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ['LOCALAPPDATA'])/'CodexOps/acceptance-0.8'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(source):
    selected = [p for p in source.rglob('*.py') if not any(part in ('.venv','__pycache__','verification','tests') for part in p.parts)]
    selected += list((source/'bin').glob('*.exe'))
    selected += [source/name for name in ('pyproject.toml','uv.lock','hooks/hooks.json')]
    selected += list((source/'skills').rglob('*.md'))
    selected += [p for p in source.rglob('*.rs') if 'target' not in p.parts]
    selected += [p for name in ('Cargo.toml','Cargo.lock') for p in source.rglob(name) if 'target' not in p.parts]
    return {p.relative_to(source).as_posix():digest(p) for p in selected if p.is_file()}


def profile_hashes(home):
    paths = [home/'config.toml']
    paths += [p for p in (home/'plugins/cache').rglob('*') if p.is_file() and 'codex-ops' in p.parts and p.suffix in ('.json','.md')]
    return {p.relative_to(home).as_posix():digest(p) for p in paths}


def freeze(destination=None):
    configs = {}
    for arm,version in (('v061','0.6.1'),('v070','0.7.0'),('v080','0.8.0')):
        area = PRIVATE/version
        profile = json.loads((area/'profile.json').read_text(encoding='utf-8'))
        selected = native_profile(version)
        source,home = Path(profile['source']),Path(selected['home'])
        if arm == 'v080':
            quality = json.loads((ROOT/'verification/quality/crap.json').read_text())
            for name, expected in quality['sourceSha256'].items():
                assert digest(source/name)==expected, 'Measured candidate source changed: '+name
            profile['sourceSha256'] = quality['sourceSha256']
            (area/'profile.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
        else:
            for name, expected in profile['sourceSha256'].items():
                assert digest(source/name)==expected, 'Frozen baseline source changed: '+name
        preflight = json.loads((ROOT/'verification'/('v080-profile-'+version+'.json')).read_text())
        assert preflight['passed'] and preflight['runtime']['runtimeVersion']==version
        assert preflight['hooksTrusted']==2 and preflight['observerExactValueEquality']
        bundle = Path(os.environ['LOCALAPPDATA'])/'CodexOps/runtime'/version
        staged = json.loads((bundle/'bundle.json').read_text())
        configs[arm] = {'version':version,'package':str(source),'home':str(home),
            'executable':str(bundle/'bin/codex-ops-cli.exe'),'serverName':'codex_ops','toolCount':8,
            'pluginSelection':selected.get('pluginSelection',{}),
            'sourceSha256':source_hashes(source),'stagedSha256':staged['files'],
            'profileFilesSha256':profile_hashes(home),'nativeHooksVerified':True,'workerObserverVerified':True,
            'preflightReceipt':str(ROOT/'verification'/('v080-profile-'+version+'.json'))}
    destination = destination or ROOT/'verification/v080-native-configs.json'
    assert not destination.exists(), 'Use a separately named frozen candidate report'
    destination.write_text(json.dumps(configs,indent=2),encoding='utf-8')
    print(json.dumps({'configurations':str(destination),'arms':list(configs),'paidCalls':0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    freeze(parser.parse_args().output)
