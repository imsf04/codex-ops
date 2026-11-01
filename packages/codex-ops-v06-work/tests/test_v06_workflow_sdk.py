import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from code_host_client import Host
import sdk_workflow
import server
import session_scope
from store import Store


TOOL_NAME = 'mcp__fixture_account__ops_workflow'
TOOL = {'tool_name': {'name': TOOL_NAME}, 'name': TOOL_NAME,
        'description': 'Read-only workflow fixture', 'kind': 'function'}
RESULT_NAME = 'mcp__fixture_account__ops_result'
RESULT_TOOL = {'tool_name': {'name': RESULT_NAME}, 'name': RESULT_NAME,
               'description': 'Explicit saved-result retrieval', 'kind': 'function'}
SHELL_TOOL = {'tool_name': {'name': 'exec_command'}, 'name': 'exec_command',
              'description': 'Native shell delegation fixture', 'kind': 'function'}


class NativeWorkflowSdkTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {'CODEX_OPS_MEASUREMENT_ORIGIN': 'validation'})
        environment.start()
        self.addCleanup(environment.stop)

    def test_factory_executes_in_real_native_v8_and_preserves_native_worker_outcomes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'sample.py').write_text('first\nneedle\nlast\n', encoding='utf-8')
            (root / 'large.txt').write_text(('needle ' + '完整 ' * 400 + '\n') * 10, encoding='utf-8')
            host = Host()
            received, calls, retrievals, shells, emitted = [], [], [], [], []
            store = Store(root / 'cache')
            owner = {'session': 'chat:native-sdk', 'runtime': None, 'policy': 'test-policy'}
            source = sdk_workflow.SOURCE + '\n' + '''
const ops = createOps(tools, ALL_TOOLS, ROOT);
const foundReceipt = await ops.locate({pattern:"needle",path:"sample.py"});
const found = await ops.resolve(foundReceipt);
if (found.matches[0].text !== "needle") throw new Error("BAD_LOCATE");
const diagnosis = await ops.resolve(await ops.diagnose({log:'sample.py:2: error: test failure'}));
if (diagnosis.diagnostics[0].text !== 'sample.py:2: error: test failure') throw new Error("BAD_DIAGNOSIS");
const documents = await ops.resolve(await ops.documents({requests:[{operation:"read",args:{files:[{path:"sample.py"}]}}],query:"needle"}));
if (documents.items[0].evidence.items[0].text !== "needle") throw new Error("BAD_DOCUMENTS");
const first = await ops.resolve(await ops.incremental({files:[{path:"sample.py"}]}));
const next = await ops.resolve(await ops.incremental({files:[{path:"sample.py"}],baselineRef:first.snapshotRef}));
if (next.items[0].changes.length !== 0) throw new Error("BAD_INCREMENTAL");
const largeReceipt = await ops.incremental({files:[{path:"large.txt"}]});
if (largeReceipt.kind !== "reference") throw new Error("EXPECTED_REFERENCE");
let budgetRejected = false;
try { await ops.resolve(largeReceipt, 512); } catch { budgetRejected = true; }
if (!budgetRejected) throw new Error("RESOLVE_BUDGET_IGNORED");
let invalidBudgetRejected = false;
try { await ops.resolve(largeReceipt, 0); } catch { invalidBudgetRejected = true; }
if (!invalidBudgetRejected) throw new Error("INVALID_RESOLVE_BUDGET");
const large = await ops.resolve(largeReceipt, 65536);
if (large.items[0].items.length !== 10 || large.items[0].items[9].text !== "needle " + "完整 ".repeat(400)) throw new Error("RAW_REFERENCE_CHANGED");
const failed = await ops.runAndDiagnose({cmd:"fixture-failure"}, {before:0,after:0});
if (failed.shell.exit_code !== 7 || failed.shell.output !== "sample.py:2: error: shell failure") throw new Error("RAW_SHELL_CHANGED");
if ((await ops.resolve(failed.diagnosis)).diagnostics[0].text !== failed.shell.output) throw new Error("SHELL_DIAGNOSIS_MISSING");
const running = await ops.runAndDiagnose({cmd:"fixture-running"});
if (running.state !== "running" || running.shell.session_id !== 42 || running.diagnosis !== null) throw new Error("RUNNING_SHELL_CHANGED");
const successful = await ops.runAndDiagnose({cmd:"fixture-success"});
if (successful.shell.exit_code !== 0 || successful.diagnosis !== null) throw new Error("SUCCESS_REEXECUTED");
let overrideRejected = false;
try { await ops.runAndDiagnose({cmd:"never-called"}, {log:"unrelated"}); } catch { overrideRejected = true; }
if (!overrideRejected) throw new Error("UNRELATED_LOG_ACCEPTED");
let refused = false;
try { createOps(tools, [], ROOT); } catch { refused = true; }
if (!refused) throw new Error("AMBIGUOUS_DISCOVERY_ACCEPTED");
text("SDK_NATIVE_OK");
'''.replace('ROOT', json.dumps(str(root)))
            try:
                host.open()
                host.request(2, {'method': 'session/execute', 'sessionId': 'probe', 'request': {
                    'tool_call_id': 'call_sdk', 'enabled_tools': [TOOL, RESULT_TOOL, SHELL_TOOL], 'source': source,
                    'yield_time_ms': 1000, 'max_output_tokens': 1000}})
                next_id = 3
                while True:
                    frame = host.receive(timeout=15)
                    received.append(frame)
                    if frame.get('type') == 'delegate/request':
                        request = frame['request']
                        self.assertEqual(request['type'], 'tool/invoke')
                        invocation = request['invocation']
                        name = invocation['tool_name']['name']
                        args = invocation['input']
                        with session_scope.bind(owner):
                            if name == TOOL_NAME:
                                calls.append(args['operation'])
                                result = server._workflow(store, **args, ctx=None)
                            elif name == RESULT_NAME:
                                retrievals.append(args)
                                result = store.result(**args)
                            else:
                                self.assertEqual(name, 'exec_command')
                                shells.append(args)
                                results = {'fixture-failure': {'exit_code': 7, 'output': 'sample.py:2: error: shell failure'},
                                           'fixture-running': {'session_id': 42, 'exit_code': None, 'output': 'still running'},
                                           'fixture-success': {'exit_code': 0, 'output': 'passed'}}
                                result = results[args['cmd']]
                        wrapped = result if name == 'exec_command' else {'structuredContent': result} if len(calls) % 2 else {
                            'structuredContent': None, 'content': [{'type': 'text', 'text': json.dumps(result)}]}
                        host.send({'type': 'delegate/response', 'id': frame['id'], 'result': {
                            'status': 'ok', 'value': {'type': 'tool/result', 'result': wrapped}}})
                        continue
                    state = frame.get('result', {}).get('value', {})
                    if frame.get('type') == 'operation/response' and state.get('type') == 'wait/completed':
                        state = state['outcome']['LiveCell']
                    elif frame.get('type') != 'execute/initialResponse':
                        continue
                    outcome = state.get('Result', state.get('Yielded'))
                    emitted.extend(item['text'] for item in outcome['content_items'] if item['type'] == 'input_text')
                    if 'Result' in state:
                        self.assertIsNone(outcome['error_text'], outcome)
                        break
                    host.request(next_id, {'method': 'session/wait', 'sessionId': 'probe', 'request': {
                        'cell_id': outcome['cell_id'], 'yield_time_ms': 1000}})
                    next_id += 1
                self.assertEqual(calls, ['locate', 'diagnose', 'documents', 'incremental', 'incremental', 'incremental', 'diagnose'])
                self.assertGreater(len(retrievals), 1)
                self.assertEqual([s['cmd'] for s in shells], ['fixture-failure', 'fixture-running', 'fixture-success'])
                self.assertTrue(all(s['workdir'] == str(root) for s in shells))
                self.assertIn('SDK_NATIVE_OK', emitted)
                self.assertEqual((root / 'sample.py').read_text(), 'first\nneedle\nlast\n')
                report = {'nativeV8': True, 'nativeReadWorker': True, 'operations': calls,
                          'realServerReceipts': True, 'explicitReferenceRetrievals': len(retrievals),
                          'nativeShellDelegationFixtures': len(shells), 'nativeShellPermissionsTestedHere': False,
                          'rawOutcomeAssertions': True, 'registryModified': False,
                          'externalModelCalls': False, 'frames': len(received)}
                directory = Path(__file__).resolve().parents[1] / 'verification'
                directory.mkdir(exist_ok=True)
                (directory / 'workflow-sdk-native.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            finally:
                store.close()
                host.close()
                host.process.stdout.close()
                host.process.stderr.close()


if __name__ == '__main__':
    unittest.main()
