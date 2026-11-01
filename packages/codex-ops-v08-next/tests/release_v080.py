"""Read-only release gates shared by local packaging and promotion helpers."""
import hashlib
import json
from pathlib import Path

VERSION = '0.8.0'


def read(path):
    if not path.is_file():
        raise ValueError('Pending required release receipt: ' + str(path))
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files(base, hashes):
    base = Path(base).resolve()
    for name, expected in hashes.items():
        path = base / name
        if not path.resolve().is_relative_to(base):
            raise ValueError('Receipt path leaves its source: ' + name)
        if digest(path) != expected:
            raise ValueError('Validated file changed: ' + str(path))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _quality(source):
    quality = read(source / 'verification/quality/crap.json')
    require(quality['above6'] == 0 and quality['maximum'] <= 6, 'Python CRAP gate failed')
    verify_files(source, quality['sourceSha256'])
    rust = read(source / 'verification/rust-quality/latest.json')
    require(rust['above6'] == 0 and rust['maximum'] <= 6, 'Rust CRAP gate failed')
    verify_files(source, rust['sourceSha256'])
    require(digest(source / 'rust-kernel/Cargo.lock') == rust['cargoLockSha256'], 'Rust lock changed')
    require(rust['upstream']['unchanged'], 'Upstream reuse changed after Rust verification')
    verify_files(source.parents[1], rust['upstream']['sourceSha256'])
    return quality, rust


def _condition(source, costs):
    condition = costs['conditionHashes']['v080']
    require(Path(condition['package']).resolve() == source.resolve(), 'Final trial used a different candidate')
    verify_files(source, condition['sourceSha256'])
    runtime = Path(condition['executable']).parents[1]
    verify_files(runtime, condition['stagedSha256'])
    verify_files(condition['home'], condition['profileFilesSha256'])
    require(condition['nativeHooksVerified'] and condition['workerObserverVerified'], 'Trial preflight incomplete')
    return condition, runtime


def validate(source):
    source = Path(source).resolve()
    require(read(source / '.codex-plugin/plugin.json')['version'] == VERSION, 'Unexpected plugin version')
    quality, rust = _quality(source)
    costs = read(source / 'verification/v080-cost-summary.json')
    require(costs.get('finalCandidate') is True, 'Final whole-model acceptance is still pending')
    require(costs.get('costGatePassed') is True, 'Fresh model cost/adoption gate has not passed')
    require(costs.get('releaseGatePassed') is True, 'Joint quality/native/cost release approval is pending')
    require(costs['sourceSha256'] == quality['sourceSha256'], 'Model and Python quality sources differ')
    require(costs['rustSourceSha256'] == rust['sourceSha256'], 'Model and Rust quality sources differ')
    require('bin/codex-ops-kernel.exe' in costs['binarySha256'], 'Measured Rust binary hash is required')
    verify_files(source, costs['binarySha256'])
    condition, runtime = _condition(source, costs)
    previous = read(source / 'verification/v080-native-final-summary.json')
    require(previous['passed'] and previous['completedCases'] == 15, 'Native transport suite incomplete')
    current = read(source / 'verification/v080-native-friction-current.json')
    require(current['passed'], 'Fresh native composite failed')
    require(current['sourceSha256'] == quality['sourceSha256'], 'Fresh native composite used different sources')
    require(current['runtimeFiles'] == condition['stagedSha256'], 'Fresh native composite used different runtime files')
    require(current['rustBinarySha256'] == costs['binarySha256']['bin/codex-ops-kernel.exe'],
            'Fresh native composite used a different Rust kernel')
    return {'quality': quality, 'rust': rust, 'costs': costs, 'condition': condition,
            'runtime': runtime, 'native': current}
