import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time


def child(package, fixture):
    sys.path.insert(0, str(package))
    import files
    import investigate
    original_popen = subprocess.Popen
    launches = [0]
    def start(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        launches[0] += 1
        return process
    subprocess.Popen = start
    samples = []
    for _ in range(7):
        launches[0] = 0
        started = time.perf_counter()
        result = investigate.run(str(fixture), {'question': 'Where does clamp_value cap DEFAULT_LIMIT?',
            'anchors': ['clamp_value', 'DEFAULT_LIMIT'], 'paths': ['example.py'], 'maxBytes': 8192}, files.run)
        elapsed = (time.perf_counter() - started) * 1000
        assert result['evidenceState'] == 'collected', result
        expected = (fixture / 'example.py').read_text().splitlines()
        for row in result['items']:
            assert row['text'] == expected[row['location']['line'] - 1]
        assert any('return min' in row['text'] for row in result['items'])
        samples.append({'milliseconds': elapsed, 'sourceLines': len(result['items']),
                        'workerStarts': launches[0]})
    print(json.dumps({'package': str(package), 'medianMs': statistics.median(s['milliseconds'] for s in samples),
                      'samples': samples}))


def main():
    candidate = Path(__file__).resolve().parents[1]
    if len(sys.argv) == 3:
        child(Path(sys.argv[1]), Path(sys.argv[2]))
        return
    with tempfile.TemporaryDirectory(prefix='codex-ops-kernel-profile-') as directory:
        fixture = Path(directory)
        (fixture / 'example.py').write_text('DEFAULT_LIMIT = 17\n\ndef clamp_value(value):\n    return min(value, DEFAULT_LIMIT)\n')
        env = dict(os.environ, CODEX_OPS_STORE=str(fixture / '.cache'), CODEX_OPS_MEASUREMENT_ORIGIN='validation')
        results = []
        for package in (candidate.parent / 'codex-ops', candidate):
            process = subprocess.run([sys.executable, __file__, str(package), str(fixture)],
                env=env, capture_output=True, text=True, check=True)
            results.append(json.loads(process.stdout))
        report = {'scope': 'Same fixed readonly fixture, seven serial in-process calls per version; first sample retained. Excludes MCP/model latency and process cold start. Exact selected source lines and key function body asserted.',
                  'versions': results}
        (candidate / 'verification/v080-kernel-profile.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({'mediansMs': [row['medianMs'] for row in results]}))


if __name__ == '__main__':
    main()
