"""Exercise actual native V8 with a transparent presentation bridge and full tool data."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from code_host_client import Host
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import Store

ROOT = Path(__file__).resolve().parents[1]
VALUE = {'records': [{'id': i, 'body': '完整' * 80} for i in range(200)], 'last': 199, 'bool': False, 'nil': None}
TOOL = {'tool_name': {'name': 'fixture'}, 'name': 'fixture', 'description': 'Deterministic fixture', 'kind': 'function'}
ASSERT = '''if(r.records.length!==200 || r.records[199].id!==199 || r.bool!==false || r.nil!==null || r.records[0].body!=='完整'.repeat(80))throw new Error('RAW_CHANGED');'''


def run(case, bridge):
    folder = Path(tempfile.mkdtemp(prefix='codex-ops-host-'))
    store_path = folder / 'store'
    if case == 'storage_failure':
        store_path.write_text('intentionally unavailable cache')
    host = Host(bridge=bridge, env={**os.environ, 'CODEX_OPS_STORE': str(store_path)})
    initial = 'const r=await tools.fixture({});' + ASSERT
    middle = {'text': 'text(r);', 'notify': 'notify(r);',
              'yield': 'text(r);await yield_control();await new Promise(resolve=>setTimeout(resolve,100));notify(r);text(r);',
              'error': 'text(r);throw new Error("EXPECTED_SCRIPT_ERROR");',
              'storage_failure': 'text(r);'}[case]
    source = initial + middle + ASSERT + 'text("RAW_INTACT");'
    received, emitted, delegates = [], [], []
    outcome = None
    try:
        host.open()
        host.request(2, {'method': 'session/execute', 'sessionId': 'probe', 'request': {
            'tool_call_id': 'call_probe', 'enabled_tools': [TOOL], 'source': source,
            'yield_time_ms': 1000, 'max_output_tokens': 100000}})
        next_id = 3
        while True:
            frame = host.receive(timeout=15)
            received.append(frame)
            kind = frame.get('type')
            if kind == 'delegate/request':
                request = frame['request']
                if request['type'] == 'tool/invoke':
                    assert request['invocation']['tool_name']['name'] == 'fixture'
                    assert request['invocation']['input'] == {}
                    value = {'type': 'tool/result', 'result': VALUE}
                else:
                    assert request['type'] == 'notification/send'
                    emitted.append(request['text'])
                    value = {'type': 'notification/delivered'}
                response = {'type': 'delegate/response', 'id': frame['id'], 'result': {'status': 'ok', 'value': value}}
                delegates.append(response)
                host.send(response)
                continue
            state = frame.get('result', {}).get('value', {})
            if kind == 'operation/response' and state.get('type') == 'wait/completed':
                state = state['outcome']['LiveCell']
            elif kind != 'execute/initialResponse':
                continue
            outcome = state.get('Result', state.get('Yielded'))
            assert isinstance(outcome, dict), frame
            emitted.extend(item['text'] for item in outcome['content_items'] if item['type'] == 'input_text')
            if 'Result' in state:
                break
            host.request(next_id, {'method': 'session/wait', 'sessionId': 'probe', 'request': {
                'cell_id': outcome['cell_id'], 'yield_time_ms': 1000}})
            next_id += 1
        if case == 'error':
            assert 'EXPECTED_SCRIPT_ERROR' in outcome['error_text'], outcome
            assert not any('"kind":"reference"' in text for text in emitted)
        else:
            assert outcome['error_text'] is None and 'RAW_INTACT' in emitted, outcome
        references = []
        for text in emitted:
            try:
                value = json.loads(text)
            except ValueError:
                continue
            if isinstance(value, dict) and value.get('kind') == 'reference':
                references.append(value['ref'])
        expected_refs = 0 if not bridge or case in ('error', 'storage_failure') else (3 if case == 'yield' else 1)
        assert len(references) == expected_refs, (case, references)
        if references:
            saved = Store(store_path)
            try:
                for ref in references:
                    assert json.loads(saved.get(ref)) == VALUE, 'Presentation observation not recoverable'
            finally:
                saved.close()
        assert delegates[0]['result']['value']['result'] == VALUE, 'Delegate input was changed'
        (folder / 'host-frames.json').write_text(json.dumps(received, ensure_ascii=False, indent=2), encoding='utf-8')
        return {'case': case, 'bridge': bridge, 'emittedBytes': sum(len(text.encode()) for text in emitted),
                'references': len(references), 'rawValueAssertion': case != 'error',
                'scriptErrorPreserved': case == 'error', 'frameCount': len(received), 'evidence': str(folder)}
    finally:
        host.close()


reports = []
for case in ['text', 'notify', 'yield', 'error', 'storage_failure']:
    baseline = run(case, False)
    compacted = run(case, True)
    if case in ('text', 'notify', 'yield'):
        assert compacted['emittedBytes'] < baseline['emittedBytes'] / 10
    else:
        assert compacted['emittedBytes'] == baseline['emittedBytes']
    reports.extend([baseline, compacted])
    print(f"PASS {case}: {baseline['emittedBytes']} -> {compacted['emittedBytes']} bytes", flush=True)
from native_cli import native_cli
binary = Path(native_cli()).with_name('codex-code-mode-host.exe')
summary = {'passed': 10, 'hostPath': str(binary), 'hostSha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
           'rawDelegateValuePreserved': True, 'sourceContainsCaptureCall': False,
           'productionInstalled': False, 'reports': reports}
(ROOT / 'verification/code-host-report.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
