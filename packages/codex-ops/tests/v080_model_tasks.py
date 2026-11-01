"""Frozen legacy producers plus four independently labelled holdout tasks."""
import hashlib
import json
from pathlib import Path

import model_tasks
import v070_model_tasks as legacy
from v070_fixture_continuation import prepare_task as legacy_prepare

LEGACY = legacy.TASKS
HOLDOUT = ('holdout_code_test_config', 'holdout_document_conflict',
           'holdout_changed_resume', 'holdout_terminal_failure')
TASKS = LEGACY + HOLDOUT
OPPORTUNITIES = {
    **{name: ['investigate','locate'] for name in ('code_location','configuration_order','chinese_anchor',
                                         'chinese_domain','medium_exact_source','source_revised_during_task')},
    'conflicting_documents':['documents','investigate'], 'late_log':['diagnose'],
    'document_lookup_tariff':['documents','investigate'], 'repair_tests_config':['investigate','locate','verify','diagnose'],
    'long_command_failure':['verify','diagnose'], 'resume_partial_work':['working_set','documents','incremental','investigate'],
    'holdout_code_test_config':['investigate','locate'], 'holdout_document_conflict':['documents','investigate'],
    'holdout_changed_resume':['working_set','incremental','investigate','locate'], 'holdout_terminal_failure':['verify','diagnose']}
OPPORTUNITIES['source_revised_during_task'].append('incremental')


def code_test_config(root):
    return legacy.answer(root, {
        'lib/transport/delay.py':'def limit_delay(delay_ms, ceiling_ms):\n    return min(max(delay_ms, 0), ceiling_ms)\n',
        'lib/transport/client.py':'from .delay import limit_delay\ndef schedule(delay, config):\n    return limit_delay(delay, config["ceiling_ms"])\n',
        'checks/regression/test_delay.py':'from lib.transport.delay import limit_delay\ndef test_negative_delay():\n    assert limit_delay(-5, 4200) == 0\n',
        'settings/production.json':'{"ceiling_ms":4200}\n',
        'generated/coverage/old.txt':'Archived implementation: delay_ms is returned unchanged.\n'*800},
        'Determine how production schedule handles a negative delay and a delay of 9000ms. '
        'Identify implementation, caller, regression test and configuration paths. Report negative_ms and large_ms '
        '(integers), implementation, caller, test, configuration (relative paths).',
        {'negative_ms':0,'large_ms':4200,'implementation':'lib/transport/delay.py',
         'caller':'lib/transport/client.py','test':'checks/regression/test_delay.py',
         'configuration':'settings/production.json'})


def document_conflict(root):
    model_tasks.write(root, 'orders.csv', 'order,tier\nK-18,business\n')
    model_tasks.write(root, 'draft-policy.md', '# Unapproved draft\nBusiness tier retention: 14 days.\n')
    model_tasks.docx(root/'approved-policy.docx', [
        'Approved retention policy, revision R7.', 'Business tier retention is 45 days.',
        'Unapproved drafts have no authority over this policy.'])
    return {'spec':'Reconcile retention for order K-18 using the order tier and approved policy. '
            'Write answer.json with order (string), days (integer), authority (relative path), '
            'rejected_days (integer), rejected_reason (string unapproved_draft).'+model_tasks.SUFFIX,
            'answer':{'order':'K-18','days':45,'authority':'approved-policy.docx',
                      'rejected_days':14,'rejected_reason':'unapproved_draft'},
            'preserved':model_tasks.snapshots(root)}


def changed_resume(root):
    result = legacy.answer(root, {
        'runtime.py':'def active_limit(settings):\n    return settings["workers"]\n',
        'settings.json':'{"workers":3}\n',
        'checks/test_workers.py':'from runtime import active_limit\ndef test_configurable():\n    assert active_limit({"workers":7}) == 7\n'},
        'The operator has now changed settings.json. Recheck the current configuration and update answer.json '
        'with workers (integer), implementation and test (relative paths).',
        {'workers':7,'implementation':'runtime.py','test':'checks/test_workers.py'})
    result['phaseOne'] = 'Inspect the worker setting, implementation and its regression test. Write answer.json with workers (integer), implementation and test (relative paths).'
    result['phaseChange'] = {'settings.json':'{"workers":7}\n'}
    result['preserved']['settings.json'] = hashlib.sha256(result['phaseChange']['settings.json'].encode()).hexdigest()
    return result


def terminal_failure(root):
    script = ('import time\nfrom pathlib import Path\n'
              'for i in range(1000): print(f"INFO stage {i} complete")\n'
              'print("START delayed verification", flush=True)\ntime.sleep(12)\n'
              'print("ERROR HOLDOUT_FORMAT expected=R7 observed=R6", flush=True)\n'
              'Path("terminal.receipt").write_bytes(b"finished-exit-9\\n")\nraise SystemExit(9)\n')
    result = legacy.answer(root, {'run_terminal.py':script},
        'In PowerShell, execute exactly `python run_terminal.py; exit $LASTEXITCODE` so the shell preserves the Python process exit code. '
        'Wait for its actual final exit. Diagnose the final error. '
        'Report exit_code (integer), error, expected and observed (strings). Preserve the script.',
        {'exit_code':9,'error':'HOLDOUT_FORMAT','expected':'R7','observed':'R6'})
    result['requiredFiles'] = {'terminal.receipt':'finished-exit-9\n'}
    result['executionRequired'] = 'run_terminal.py'
    result['executionExit'] = 9
    return result


BUILDERS = dict(zip(HOLDOUT, (code_test_config, document_conflict, changed_resume, terminal_failure)))


def prepare_task(name, root):
    if name not in BUILDERS:
        result = legacy_prepare(name, root)
        if name == 'long_command_failure':
            result['executionExit'] = 7
        return result
    root.mkdir(parents=True)
    result = BUILDERS[name](root)
    result['fixtureRevision'] = 'v080-holdout-1'
    return result


def evaluate_task(name, root, expected):
    return legacy.evaluate_task(name, root, expected)


def solve_for_self_test(name, root, expected):
    legacy.solve_for_self_test(name, root, expected)


def execution_observed(events, expected):
    filename = expected.get('executionRequired')
    if filename is None:
        return True
    for event in events:
        item = event.get('params', {}).get('item', {})
        if item.get('type') != 'commandExecution':
            continue
        if filename in json.dumps(item.get('command', '')):
            return True
    return False


def execution_exit_observed(events, expected):
    filename = expected.get('executionRequired')
    if filename is None:
        return True
    return any(event.get('method') == 'item/completed'
               and event.get('params', {}).get('item', {}).get('type') == 'commandExecution'
               and filename in json.dumps(event['params']['item'].get('command', ''))
               and event['params']['item'].get('exitCode') == expected['executionExit']
               for event in events)
