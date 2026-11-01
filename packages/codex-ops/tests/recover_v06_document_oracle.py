"""Recover original DOCX expectation from a pre-write native listing, without a model call."""
import datetime
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from model_tasks import prepare_task
from native_cli import native_cli
from run_model_benchmark import Host, native_evaluate, save_report

package = Path(__file__).resolve().parents[1]
suite_path = package / 'verification/model-v06-suite.json'
suite = json.loads(suite_path.read_text())
row = next(item for item in suite['reports'] if item['key'] == '1-document_lookup-v05')
events = Path(row['eventsPath'])
first = next(json.loads(line)['params']['item'] for line in events.read_text(encoding='utf-8').splitlines()
             if json.loads(line).get('params', {}).get('item', {}).get('type') == 'commandExecution')
assert 'Get-ChildItem' in first['command']
assert 'policy.docx        990 2026/10/29 11:49:23' in first['aggregatedOutput']
timestamp = datetime.datetime(2026, 10, 29, 11, 49, 23).timetuple()
with tempfile.TemporaryDirectory(prefix='codex-ops-docx-reconstruct-') as directory:
    root = Path(directory) / 'expected'
    with patch('zipfile.time.localtime', return_value=timestamp):
        expected = prepare_task('document_lookup', root)
    assert (root / 'policy.docx').stat().st_size == 990
workspace = Path(row['workspace'])
host = Host(native_cli(), workspace, Path(row['storeRoot']), [], artifact_prefix='oracle-docx-recovery-')
try:
    host.request('initialize', {'clientInfo': {'name': 'codex-ops-docx-oracle-recovery', 'version': '0.6.0'},
                                'capabilities': {'experimentalApi': True}})
    host.send({'method': 'initialized'})
    outcome = native_evaluate(host, row['task'], workspace, expected)
finally:
    host.close()
report = {'key': row['key'], 'modelCalls': 0, 'originalOutcome': row['outcome'], 'correctedOutcome': outcome,
          'expectedPreservedHashes': expected['preserved'],
          'expectationBasis': 'Deterministic original fixture builder and native pre-write listing timestamp; ZIP stores seconds rounded down to even',
          'originalListing': first, 'eventTraceSha256': hashlib.sha256(events.read_bytes()).hexdigest()}
save_report(package / 'verification/model-v06-document-oracle-recovery.json', report)
print(json.dumps({'passed': outcome['passed'], 'checks': outcome.get('checks'), 'inputPreservation': outcome.get('failures')}))
