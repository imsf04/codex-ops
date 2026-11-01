"""Twelve independent, tool-neutral outcome fixtures for the 0.7 paired study."""
import json
from pathlib import Path

import model_tasks
from model_tasks import write, snapshots, SUFFIX

TASKS = ('code_location', 'configuration_order', 'chinese_anchor', 'chinese_domain',
         'medium_exact_source', 'conflicting_documents', 'late_log', 'document_lookup_tariff',
         'source_revised_during_task', 'repair_tests_config', 'long_command_failure', 'resume_partial_work')


def answer(root, files, prompt, value):
    for name, content in files.items():
        write(root, name, content)
    return {'spec': prompt + ' Write answer.json with exactly the named fields and types.' + SUFFIX,
            'answer': value, 'preserved': snapshots(root)}


def configuration_order(root):
    return answer(root, {
        'src/config.py': 'def select_port(cli, environment, defaults):\n    if "port" in cli:\n        return cli["port"]\n    return environment.get("PORT", defaults["port"])\n',
        'config/defaults.json': '{"port":8080}',
        'docs/old-plan.md': 'Historical proposal: environment wins over command-line arguments. Not implemented.\n',
        'tests/test_config.py': 'from src.config import select_port\ndef test_explicit_zero():\n    assert select_port({"port":0}, {"PORT":9000}, {"port":8080}) == 0\n'},
        'Determine actual select_port precedence. For cli port=0, environment PORT=9000 and default port=8080, '
        'report selected (integer), precedence (array of cli/environment/default), path and test (relative paths).',
        {'selected': 0, 'precedence': ['cli', 'environment', 'default'], 'path': 'src/config.py', 'test': 'tests/test_config.py'})


def chinese_anchor(root):
    return answer(root, {'src/jobs/retry.py': 'JOB_RETRY_LIMIT = 4\ndef retry_job(attempt):\n    return attempt < JOB_RETRY_LIMIT\n',
        'src/network/retry.py': 'HTTP_RETRY_LIMIT = 9\ndef retry_request(attempt):\n    return attempt <= HTTP_RETRY_LIMIT\n',
        'docs/queue.md': '后台任务最多进行四轮尝试，判断依据是零起始的 attempt。\n'},
        '查清 JOB_RETRY_LIMIT 如何限制后台任务重试。输出 path（函数所在相对路径）、symbol（函数名）、'
        'limit（整数）和 attempt4（attempt=4 时的布尔结果）。',
        {'path': 'src/jobs/retry.py', 'symbol': 'retry_job', 'limit': 4, 'attempt4': False})


def chinese_domain(root):
    return answer(root, {'docs/发票规则.md': '# 尾差归属\n分摊产生的剩余一分钱归到金额最大的项目；金额相同归到输入最前的项目。实现见 src/allocation.py。\n',
        'src/allocation.py': 'def remainder_owner(amounts):\n    return max(range(len(amounts)), key=lambda i: amounts[i])\n',
        'docs/库存规则.md': '库存余量分配到最早入库的批次，与发票尾差无关。\n'},
        '查明发票分摊出现尾差时归到哪一项。输出 source（实现的相对路径）、rule（largest_first）、'
        'owner_index（金额 [20, 35, 35] 对应零起始索引）。',
        {'source': 'src/allocation.py', 'rule': 'largest_first', 'owner_index': 1})


def medium_exact_source(root):
    lines = ['# unrelated source context ' + str(n) for n in range(360)]
    lines[173] = 'EXACT_RECORD = "south|東京|\\t|quote=\\\"|checksum=7c19"'
    return answer(root, {'src/records.py': '\n'.join(lines)+'\n'},
        'Find EXACT_RECORD in src/records.py. Report line (1-based integer) and source_text '
        '(the exact complete source line, preserving Unicode, backslashes and quotes; do not evaluate the Python literal).',
        {'line': 174, 'source_text': lines[173]})


def conflicting_documents(root):
    model_tasks.docx(root/'policy.docx', ['Current approved policy, revision 8.',
        'Product KITE has a 24-month warranty from delivery.', 'Clearance items retain the same warranty.'])
    write(root, 'draft.md', 'UNAPPROVED DRAFT revision 9: clearance warranty could become 6 months.\n')
    write(root, 'orders.csv', 'order,product,clearance,delivery\nO-77,KITE,true,2026-01-15\n')
    return {'spec': 'Resolve the warranty for order O-77 using approved policy rather than an unapproved draft. '
            'Write answer.json with order (string), months (integer), authority (filename), '
            'rejected_months (integer) and rejection_reason (unapproved_draft).' + SUFFIX,
            'answer': {'order':'O-77','months':24,'authority':'policy.docx','rejected_months':6,'rejection_reason':'unapproved_draft'},
            'preserved': snapshots(root)}


def late_log(root):
    body = 'INFO check passed\n'*5000 + 'ERROR EXPORT_SCHEMA expected=3 observed=2 source=src/export.py:2\n'
    return answer(root, {'build.log': body, 'src/export.py': 'def export_schema():\n    return 2\n'},
        'Identify the actual failure after the successful checks in build.log. Report error (code), '
        'line (original log line), expected and observed (integers), source (relative path) and source_line (integer).',
        {'error':'EXPORT_SCHEMA','line':5001,'expected':3,'observed':2,'source':'src/export.py','source_line':2})


def source_revised_during_task(root):
    result = answer(root, {'config.json': '{"window":17}\n', 'notes.md': 'Previous inspection: window=17.\n'},
        'Inspect config.json, then change window from 17 to 31. Re-read current source and report '
        'previous (integer), current (integer), and notes_stale (boolean). Preserve notes.md.',
        {'previous':17,'current':31,'notes_stale':True})
    result['preserved'].pop('config.json')
    result['requiredJson'] = {'config.json': {'window':31}}
    return result


def long_command_failure(root):
    script = ('import time\nfrom pathlib import Path\nprint("START check", flush=True)\ntime.sleep(2)\n'
              'print("ERROR VERIFY_SIGNATURE expected=v3 observed=v2", flush=True)\n'
              'Path("execution.receipt").write_text("completed-with-exit-7\\n")\nraise SystemExit(7)\n')
    result = answer(root, {'run_probe.py':script},
        'Run run_probe.py with Python, wait for its final state, and diagnose its failure. '
        'Report exit_code (integer), error (code), expected and observed (strings). Do not edit the script.',
        {'exit_code':7,'error':'VERIFY_SIGNATURE','expected':'v3','observed':'v2'})
    result['requiredFiles'] = {'execution.receipt':'completed-with-exit-7\n'}
    result['executionRequired'] = 'run_probe.py'
    return result


def resume_partial_work(root):
    result = answer(root, {'progress.md': 'Task: migrate ports to 8400. api done, worker and report pending.\n',
        'api.json':'{"port":8400}\n','worker.json':'{"port":8300}\n','untouched.txt':'preserve me\n'},
        'Resume the migration described by progress.md. Confirm current files, finish only the pending worker '
        'port change and write answer.json with api_port, worker_port (integers), previously_completed (array containing api). '
        'Preserve api.json, progress.md and untouched.txt.',
        {'api_port':8400,'worker_port':8400,'previously_completed':['api']})
    result['preserved'].pop('worker.json')
    result['requiredJson'] = {'worker.json':{'port':8400}}
    return result


BUILDERS = {name: globals()[name] for name in TASKS if name in globals()}


def prepare_task(name, root):
    if name not in BUILDERS:
        return model_tasks.prepare_task(name, root)
    root.mkdir(parents=True)
    return BUILDERS[name](root)


def evaluate_task(name, root, expected):
    result = model_tasks.evaluate_task(name, root, expected)
    failures = list(result.get('failures', []))
    for filename, value in expected.get('requiredJson', {}).items():
        try:
            actual = json.loads((root/filename).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            actual = None
        if actual != value:
            failures.append({'file':filename,'reason':'required final JSON differs'})
    for filename, value in expected.get('requiredFiles', {}).items():
        path = root/filename
        if not path.is_file() or path.read_bytes() != value.encode():
            failures.append({'file':filename,'reason':'required final bytes differ'})
    return {**result,'passed':result['passed'] and not failures,'failures':failures,'oracleVersion':'v070.1-frozen'}


def solve_for_self_test(name, root, expected):
    model_tasks.solve_for_self_test(name, root, expected)
    for filename,value in expected.get('requiredJson', {}).items():
        write(root,filename,json.dumps(value))
    for filename,value in expected.get('requiredFiles', {}).items():
        write(root,filename,value)
