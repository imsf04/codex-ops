import datetime
from functools import cache
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

import lizard

ROOT = Path(__file__).resolve().parents[1]
CRATE = ROOT / 'rust-kernel'
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')
REPORT = ROOT / 'verification/rust-quality' / STAMP


def run(name, command, env):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, env=env,
                            capture_output=True, text=True, encoding='utf-8')
    (REPORT / (name + '.stdout')).write_text(result.stdout, encoding='utf-8')
    (REPORT / (name + '.stderr')).write_text(result.stderr, encoding='utf-8')
    result.check_returncode()
    return result.stdout


def environment():
    REPORT.mkdir(parents=True)
    env = dict(os.environ, RUSTFLAGS='-C instrument-coverage',
               CARGO_TARGET_DIR=str(CRATE / 'target/coverage'),
               LLVM_PROFILE_FILE=str(REPORT / 'run-%p-%m.profraw'),
               CODEX_OPS_MEASUREMENT_ORIGIN='validation')
    env.pop('CARGO_ENCODED_RUSTFLAGS', None)
    return env


def executables(messages):
    records = [json.loads(line) for line in messages.splitlines() if line.startswith('{')]
    return [Path(r['executable']) for r in records
            if r.get('reason') == 'compiler-artifact' and r.get('executable') and r.get('profile', {}).get('test')]


def instrument(env):
    common = ['cargo', '--offline', '--locked', '--manifest-path', CRATE / 'Cargo.toml']
    messages = run('build-tests', [common[0], 'test', *common[1:], '--no-run', '--message-format=json'], env)
    tests = executables(messages)
    run('build-main', [common[0], 'build', *common[1:], '--bin', 'codex-ops-kernel'], env)
    for index, executable in enumerate(tests):
        run('unit-' + str(index), [executable], env)
    binary = CRATE / 'target/coverage/debug/codex-ops-kernel.exe'
    env['CODEX_OPS_KERNEL'] = str(binary)
    run('integration', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_v080_kernel.py', '-v'], env)
    run('integration-fallback', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_v080_anchor_fallback.py', '-v'], env)
    return binary, tests


def llvm_tools(env):
    compiler = Path(run('rustc-path', ['rustup', 'which', 'rustc'], env).strip())
    version = run('rustc-version', ['rustc', '-vV'], env)
    host = next(line.split(': ', 1)[1] for line in version.splitlines() if line.startswith('host:'))
    directory = compiler.parent.parent / 'lib/rustlib' / host / 'bin'
    return directory / 'llvm-profdata.exe', directory / 'llvm-cov.exe'


def exports(binary, tests, env):
    profdata, cov = llvm_tools(env)
    profiles = list(REPORT.glob('*.profraw'))
    assert profiles, 'No instrumented native coverage profiles'
    merged = REPORT / 'merged.profdata'
    run('merge', [profdata, 'merge', '-sparse', *profiles, '-o', merged], env)
    objects = [item for path in tests for item in ('--object', path)]
    sources = [p for p in (CRATE / 'src').glob('*.rs') if p.name != 'tests.rs']
    command = [cov, 'export', binary, *objects, '--instr-profile', merged, *sources]
    return sources, json.loads(run('llvm-export', command, env)), run('lcov', [*command, '--format=lcov'], env)


@cache
def source_key(path):
    return str(Path(path).resolve()).casefold()


def lines(lcov):
    output = {}
    current = None
    for line in lcov.splitlines():
        if line.startswith('SF:'):
            current = output.setdefault(source_key(line[3:]), {})
        elif line.startswith('DA:'):
            number, count, *_ = line[3:].split(',')
            current[int(number)] = int(count)
    return output


def regions(export):
    output = {}
    for dataset in export['data']:
        for function in dataset['functions']:
            for region in function['regions']:
                if region[7] == 0:
                    path = source_key(function['filenames'][region[5]])
                    key = tuple(region[:4])
                    values = output.setdefault(path, {})
                    values[key] = values.get(key, 0) + region[4]
    return output


def fraction(counts):
    assert counts, 'Coverage absent for a measured source function'
    return sum(n > 0 for n in counts) / len(counts)


def measure(source, function, line_hits, region_hits):
    statements = [count for line, count in line_hits.items() if function.start_line <= line <= function.end_line]
    blocks = [count for (start, _, end, _), count in region_hits.items()
              if function.start_line <= start and end <= function.end_line]
    coverage = min(fraction(statements), fraction(blocks))
    complexity = function.cyclomatic_complexity
    return {'path': str(source.relative_to(ROOT)), 'name': function.name,
            'start': function.start_line, 'end': function.end_line, 'complexity': complexity,
            'lineCoverage': fraction(statements), 'regionCoverage': fraction(blocks), 'coverage': coverage,
            'crap': complexity + complexity ** 2 * (1 - coverage) ** 3}


def provenance():
    upstream = ROOT.parents[1]
    tracked = subprocess.check_output(['git', 'ls-files', 'native'], cwd=upstream, text=True).splitlines()
    state = subprocess.check_output(['git', 'status', '--porcelain', '--', 'native'], cwd=upstream, text=True)
    assert not state.strip(), 'Upstream native sources differ from their recorded commit'
    return {'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upstream, text=True).strip(),
            'unchanged': True, 'sourceSha256': {name: hashlib.sha256((upstream / name).read_bytes()).hexdigest()
                                             for name in tracked}}


def test_counts():
    unit = sum(int(n) for path in REPORT.glob('unit-*.stdout')
               for n in re.findall(r'test result: ok\. (\d+) passed', path.read_text()))
    integration = sum(int(re.search(r'Ran (\d+) tests', path.read_text())[1])
                      for path in REPORT.glob('integration*.stderr'))
    return {'rustUnit': unit, 'nativePythonIntegration': integration}


def report(sources, export, lcov):
    line_hits, region_hits = lines(lcov), regions(export)
    rows = [measure(source, function, line_hits[source_key(source)], region_hits[source_key(source)])
            for source in sources for function in lizard.analyze_file(str(source)).function_list]
    rows.sort(key=lambda row: row['crap'], reverse=True)
    document = {'version': '0.8.0', 'measurement': 'Lizard Rust cyclomatic complexity; actual LLVM 21 instrumented line and code-region coverage. CRAP uses the lower fraction. Stable compiler branch/MC/DC coverage is not claimed.',
                'scope': 'All functions written in rust-kernel/src excluding its test module. Unchanged upstream crates and existing launcher shim are not newly measured by this gate.',
                'functions': len(rows), 'maximum': rows[0]['crap'], 'above6': sum(row['crap'] > 6 for row in rows),
                'sourceSha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                'rows': rows, 'evidence': str(REPORT), 'tests': test_counts(), 'upstream': provenance(),
                'cargoLockSha256': hashlib.sha256((CRATE / 'Cargo.lock').read_bytes()).hexdigest()}
    (REPORT / 'crap.json').write_text(json.dumps(document, indent=2), encoding='utf-8')
    (REPORT.parent / 'latest.json').write_text(json.dumps(document, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in document.items() if k not in ('rows','sourceSha256','upstream')}, ensure_ascii=False))
    assert document['above6'] == 0, [row for row in rows if row['crap'] > 6]


def main():
    env = environment()
    binary, tests = instrument(env)
    report(*exports(binary, tests, env))


if __name__ == '__main__':
    main()
