"""Replay the five retained absent-evidence calls with exact initial fixture bytes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import files
import investigate
import native_process
from test_v080_anchor_fallback import CODE, SOURCE

ORIGINAL = ROOT.with_name('codex-ops-v08-work') / 'verification/v080-full-1.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def original_call(row):
    for raw in Path(row['eventsPath']).read_text(encoding='utf-8').splitlines():
        event = json.loads(raw)
        item = event.get('params', {}).get('item', {})
        if event.get('method') == 'item/completed' and item.get('tool') == 'ops_workflow':
            result = json.loads(item['result']['content'][0]['text'])
            return item['arguments'], result.get('value', result)
    raise AssertionError('Original workflow invocation is missing')


def replay(row):
    args, old = original_call(row)
    expected = SOURCE if row['task'] == 'chinese_domain' else CODE
    original = Path(row['workspace'])
    provenance = {}
    with tempfile.TemporaryDirectory(prefix='codex-ops-retained-replay-') as temporary:
        root = Path(temporary)
        for name, text in expected.items():
            raw = (original / name).read_bytes()
            assert raw.decode('utf-8').replace('\r\n', '\n') == text
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            provenance[name] = sha(raw)
        assert not (root / 'answer.json').exists()
        with patch('native_process.subprocess.Popen', wraps=native_process.subprocess.Popen) as starts:
            result = investigate.run(str(root), {'question': args['question'], **args.get('args', {})}, files.run)
        assert starts.call_count == 1
        assert result['evidenceState'] == 'collected', result
        actual = {Path(item['source']['path']).relative_to(root).as_posix() for item in result['items']}
        assert 'generated/coverage/old.txt' not in actual
        required = {'docs/发票规则.md'} if row['task'] == 'chinese_domain' else set(CODE) - {'generated/coverage/old.txt'}
        assert required.issubset(actual), actual
        for item in result['items']:
            path = Path(item['source']['path'])
            assert path.read_text(encoding='utf-8').splitlines()[item['location']['line'] - 1] == item['text']
        assert all(sha((root / name).read_bytes()) == digest for name, digest in provenance.items())
        return {'key': row['key'], 'originalQuestion': args['question'], 'originalState': old['evidenceState'],
                'originalAnchors': old.get('anchors'), 'sourceBytesSha256': provenance, 'requiredPaths': sorted(required),
                'deliveredPaths': sorted(actual), 'workerStartsMeasured': starts.call_count, 'result': result,
                'sourceBytesUnchanged': True, 'answerArtifactsExcluded': True}


def main():
    report = json.loads(ORIGINAL.read_text(encoding='utf-8'))
    rows = [row for row in report['reports'] if row['condition'] == 'v080'
            and row['task'] in ('chinese_domain', 'holdout_code_test_config')
            and row['adoption']['evidence'].get('absent') == 1]
    assert len(rows) == 5
    os.environ['CODEX_OPS_MEASUREMENT_ORIGIN'] = 'validation'
    results = [replay(row) for row in rows]
    document = {'version': '0.8.0', 'passed': True, 'originalReport': str(ORIGINAL),
                'originalReportSha256': sha(ORIGINAL.read_bytes()), 'cases': results,
                'kernelSha256': sha((ROOT / 'bin/codex-ops-kernel.exe').read_bytes()),
                'sourceSha256': {name: sha((ROOT / name).read_bytes()) for name in
                    ('investigate_query.py', 'investigate_plan.py', 'investigate.py', 'evidence_packet.py')},
                'paidModelCalls': 0, 'scope': 'Deterministic evidence acquisition replay only. Original task grades and real-model costs are unchanged; no model adoption or cost improvement claim.'}
    target = ROOT / 'verification/v080-absent-evidence-replay.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': True, 'cases': len(results), 'workerStarts': [row['workerStartsMeasured'] for row in results],
                      'internalOperations': [row['result']['coverage']['kernel']['internalOperations'] for row in results],
                      'receipt': str(target)}))


if __name__ == '__main__':
    main()
