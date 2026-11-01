"""Fifteen additional independent task fixtures for the 0.6 paired evaluation."""
import copy
import importlib.util
import json
from pathlib import Path

from model_tasks import SUFFIX, docx, snapshots, write


def answer_task(root, files, spec, answer, answer_file='answer.json'):
    for name, content in files.items():
        write(root, name, content)
    return {'spec': spec + f' Write {answer_file} with exactly the requested fields.' + SUFFIX,
            'answer': answer, 'answerFile': answer_file, 'preserved': snapshots(root)}


def location_cache(root):
    files = {
        'src/cache/ttl.py': '"""Expiry is inclusive at the exact deadline."""\n\ndef expired(created_ms, now_ms, ttl_ms):\n    return now_ms >= created_ms + ttl_ms\n',
        'src/auth/ttl.py': 'def expired(last_used, now, idle):\n    return now - last_used > idle\n',
        'tests/test_cache_ttl.py': 'from src.cache.ttl import expired\n\ndef test_exact_deadline():\n    assert expired(100, 150, 50) is True\n',
        'docs/cache.md': 'Cached values expire at the inclusive absolute deadline; authentication idle windows differ.\n'}
    answer = {'path': 'src/cache/ttl.py', 'symbol': 'expired', 'line': 3,
              'boundary': 'inclusive', 'test_path': 'tests/test_cache_ttl.py', 'test_symbol': 'test_exact_deadline'}
    return answer_task(root, files, 'Locate cached-value expiry and its exact-deadline regression. Return path, symbol, line (1-based), boundary (inclusive/exclusive), test_path and test_symbol. Preserve inputs.', answer)


def location_authority(root):
    files = {
        'src/security/authorize.py': 'def may_publish(role, suspended, owner):\n    if suspended:\n        return False\n    return role == "editor" or owner\n',
        'src/ui/buttons.py': 'def may_publish(role):\n    return role != "guest"\n',
        'src/security/read.py': 'def may_read(role, suspended):\n    return role != "guest"\n',
        'tests/test_authorize.py': 'from src.security.authorize import may_publish\n\ndef test_suspended_owner_cannot_publish():\n    assert may_publish("editor", True, True) is False\n',
        'docs/security.md': 'Server authority is in src/security, not UI affordances. Suspension overrides ownership.\n'}
    answer = {'path': 'src/security/authorize.py', 'symbol': 'may_publish', 'line': 1,
              'override': 'suspended', 'test_path': 'tests/test_authorize.py', 'test_symbol': 'test_suspended_owner_cannot_publish'}
    return answer_task(root, files, 'Locate the server publish authorization function and test proving owner status cannot bypass suspension. Return path, symbol, line (1-based), override, test_path and test_symbol. Preserve inputs.', answer)


def location_rounding(root):
    files = {
        'src/billing/cents.py': 'def discounted_cents(subtotal, basis_points):\n    numerator = subtotal * (10000 - basis_points)\n    return (numerator + 5000) // 10000\n',
        'src/display/prices.py': 'def discounted_cents(value, discount):\n    return round(value * (1 - discount))\n',
        'tests/test_cents.py': 'from src.billing.cents import discounted_cents\n\ndef test_half_cent_rounds_up():\n    assert discounted_cents(101, 5000) == 51\n',
        'docs/money.md': 'Settlement uses integer half-up cents, while display formatting may use round().\n'}
    answer = {'path': 'src/billing/cents.py', 'symbol': 'discounted_cents', 'line': 1,
              'rounding': 'half-up', 'test_path': 'tests/test_cents.py', 'test_symbol': 'test_half_cent_rounds_up'}
    return answer_task(root, files, 'Locate settlement discount rounding and the half-cent regression. Return path, symbol, line (1-based), rounding, test_path and test_symbol. Preserve inputs.', answer)


def repair(root, filename, function, broken, spec, cases, solution):
    write(root, filename, broken)
    write(root, 'README.md', spec + '\n')
    # Public examples are a subset; the trusted evaluator owns the complete cases.
    public = 'import unittest\nfrom ' + filename[:-3] + ' import ' + function + '\n\nclass Examples(unittest.TestCase):\n'
    for index, case in enumerate(cases[:2]):
        public += f'    def test_{index}(self):\n        self.assertEqual({function}(*{case["args"]!r}), {case["expected"]!r})\n'
    public += '\nif __name__ == "__main__":\n    unittest.main()\n'
    write(root, 'test_examples.py', public)
    preserved = snapshots(root)
    preserved.pop(filename)
    preserved.pop('test_examples.py')
    return {'spec': spec + ' Repair ' + filename + ', add focused regressions if useful, and run tests.' + SUFFIX,
            'preserved': preserved, 'genericRepair': {'file': filename, 'function': function, 'cases': cases},
            'selfTestSolution': solution}


def repair_ranges(root):
    solution = 'def merge_ranges(ranges):\n    result = []\n    for start, end in sorted(ranges):\n        if result and start <= result[-1][1] + 1:\n            result[-1][1] = max(result[-1][1], end)\n        else:\n            result.append([start, end])\n    return result\n'
    cases = [{'args': [[[4, 5], [1, 3]]], 'expected': [[1, 5]]},
             {'args': [[[1, 9], [2, 3]]], 'expected': [[1, 9]]},
             {'args': [[]], 'expected': []}, {'args': [[[9, 9], [1, 1], [3, 4]]], 'expected': [[1, 1], [3, 4], [9, 9]]},
             {'args': [[[-3, -1], [0, 2], [8, 8]]], 'expected': [[-3, 2], [8, 8]]}]
    return repair(root, 'ranges.py', 'merge_ranges', 'def merge_ranges(ranges):\n    ranges.sort()\n    return ranges\n',
        'merge_ranges accepts integer inclusive [start,end] pairs with start<=end. Return sorted merged pairs, coalescing overlap and adjacency, retaining the furthest end. Do not mutate input.', cases, solution)


def repair_config(root):
    solution = 'import copy\ndef overlay(base, updates):\n    result = copy.deepcopy(base)\n    for key, value in updates.items():\n        if value is None:\n            result.pop(key, None)\n        elif isinstance(value, dict) and isinstance(result.get(key), dict):\n            result[key] = overlay(result[key], value)\n        else:\n            result[key] = copy.deepcopy(value)\n    return result\n'
    cases = [{'args': [{'db': {'host': 'a', 'port': 3}}, {'db': {'port': 4}}], 'expected': {'db': {'host': 'a', 'port': 4}}},
             {'args': [{'a': 1, 'b': 2}, {'a': None}], 'expected': {'b': 2}},
             {'args': [{'a': [1, 2]}, {'a': [3]}], 'expected': {'a': [3]}},
             {'args': [{'a': 0}, {'a': {'b': False}}], 'expected': {'a': {'b': False}}},
             {'args': [{}, {'a': None, 'b': '', 'c': 0}], 'expected': {'b': '', 'c': 0}}]
    return repair(root, 'config_merge.py', 'overlay', 'def overlay(base, updates):\n    base.update(updates)\n    return base\n',
        'overlay returns a deep copy: recursively merge dict/dict pairs; None deletes a key; arrays/scalars replace. Preserve false, zero and empty strings. Neither input nor nested input objects may be mutated.', cases, solution)


def repair_durations(root):
    solution = 'import re\ndef duration_ms(value):\n    match = re.fullmatch(r"([0-9]+)(ms|s|m)", value.strip())\n    if match is None:\n        return None\n    return int(match[1]) * {"ms": 1, "s": 1000, "m": 60000}[match[2]]\n'
    cases = [{'args': ['12ms'], 'expected': 12}, {'args': ['2m'], 'expected': 120000},
             {'args': [' 3s '], 'expected': 3000}, {'args': ['0ms'], 'expected': 0},
             {'args': ['4seconds'], 'expected': None}, {'args': ['-1s'], 'expected': None},
             {'args': ['1.5s'], 'expected': None}, {'args': ['7'], 'expected': None}]
    return repair(root, 'durations.py', 'duration_ms', 'def duration_ms(value):\n    return int(value[:-1]) * 1000\n',
        'duration_ms parses optional outer whitespace plus nonnegative integer and exact lowercase unit ms/s/m, returning integer milliseconds. Invalid forms return None, without exceptions. Decimal, signed, unitless and long unit names are invalid.', cases, solution)


def batch(root, initial, changed, removed, spec):
    for name, body in initial.items():
        write(root, name, body)
    preserved = snapshots(root)
    for name in (*changed, *removed):
        preserved.pop(name, None)
    return {'spec': spec + SUFFIX, 'files': changed, 'removed': removed, 'preserved': preserved}


def batch_imports(root):
    initial = {'src/api.py': 'from old_client import Client\n# old_client remains in historical notes\nclient = Client()\n',
               'src/jobs.py': 'from old_client import Client\nclient = Client()\n',
               'src/legacy.py': 'from old_client import Client\n# Keep compatibility module unchanged.\n',
               'docs/upgrade-draft.md': '# Client upgrade\nUse new_client for production callers.\n',
               'docs/obsolete.md': 'Old deployment recipe.\n'}
    changed = {name: initial[name].replace('from old_client import Client', 'from new_client import Client') for name in ('src/api.py', 'src/jobs.py')}
    changed['docs/upgrade.md'] = initial['docs/upgrade-draft.md']
    changed['migration.txt'] = 'api,jobs migrated; legacy preserved\n'
    return batch(root, initial, changed, ['docs/upgrade-draft.md', 'docs/obsolete.md'],
        'Change only the Client import in src/api.py and src/jobs.py from old_client to new_client. Preserve comments and src/legacy.py. Rename docs/upgrade-draft.md to docs/upgrade.md without changing bytes, remove docs/obsolete.md, and create migration.txt exactly "api,jobs migrated; legacy preserved" plus one newline. Verify changes.')


def batch_environment(root):
    initial = {f'config/{env}.json': json.dumps({'name': env, 'cache': {'enabled': False, 'ttl': 30}, 'audit': True}, indent=2) + '\n' for env in ('dev', 'test', 'prod')}
    initial['README.md'] = 'Keep development caching disabled.\n'
    changed = {name: body.replace('"enabled": false', '"enabled": true').replace('"ttl": 30', '"ttl": 90') for name, body in initial.items() if name in ('config/test.json', 'config/prod.json')}
    changed['config/test.backup.json'] = initial['config/test.json']
    return batch(root, initial, changed, [], 'Before editing, copy config/test.json byte-for-byte to config/test.backup.json. In test.json and prod.json only, enable cache and change ttl 30 to 90, preserving formatting, audit and names. Leave dev.json and README untouched. Verify all outputs.')


def batch_release(root):
    initial = {'releases/current.txt': 'release=2026.09\nchannel=stable\n', 'releases/next.txt': 'release=2026.10\nchannel=stable\n',
               'docs/install.md': 'Install release 2026.09.\nHistorical example: 2026.09.\n', 'docs/history.md': '2026.09 was stable.\n', 'releases/temp.txt': 'remove after release\n'}
    changed = {'releases/previous.txt': initial['releases/current.txt'], 'releases/current.txt': initial['releases/next.txt'],
               'docs/install.md': 'Install release 2026.10.\nHistorical example: 2026.09.\n'}
    return batch(root, initial, changed, ['releases/next.txt', 'releases/temp.txt'],
        'Preserve the old current release as releases/previous.txt, promote releases/next.txt to releases/current.txt and remove next.txt. Remove releases/temp.txt. Change only the first line of docs/install.md to "Install release 2026.10."; preserve historical examples and docs/history.md. Verify final contents.')


def log_compiler(root):
    lines = [f'build asset-{n:03} cached' for n in range(65)] + ['src/user.ts(8,3): error TS2322: Type string is not assignable to number.', 'build: error TASK_FAILED caused_by=TS2322', 'process exit_code=2']
    files = {'build.log': '\n'.join(lines) + '\n', 'src/user.ts': 'export interface User { age: number; }\n// user import boundary\nconst source = { age: "42" };\n\n// Conversion is required before assignment.\n\nexport const user: User = {\n  age: source.age,\n};\n',
             'docs/types.md': 'User.age is an integer, parsed at the import boundary. Compiler code TS2322 reports assignment mismatch.\n'}
    answer = {'root_cause': 'TS2322', 'file': 'src/user.ts', 'line': 8, 'observed': 'string', 'expected': 'number', 'evidence_line': 66}
    return answer_task(root, files, 'Diagnose the primary compiler failure, not TASK_FAILED. Return root_cause, file, line, observed, expected and evidence_line (1-based build.log). Preserve inputs.', answer, 'diagnosis.json')


def log_migration(root):
    lines = [f'INFO shard={n} connectivity=ok' for n in range(55)] + ['WARN cache empty; fallback succeeded', 'ERROR migration=0042 code=SCHEMA_VERSION expected=42 observed=41 database=orders', 'ERROR code=STARTUP_ABORT caused_by=SCHEMA_VERSION', 'ERROR code=SERVICE_UNAVAILABLE cause=STARTUP_ABORT']
    files = {'startup.log': '\n'.join(lines) + '\n', 'schema.json': '{"database":"orders","version":41}\n', 'migrations/0042.sql': '-- Expected version after applying: 42\nALTER TABLE orders ADD COLUMN source TEXT;\n'}
    answer = {'root_cause': 'SCHEMA_VERSION', 'database': 'orders', 'expected': 42, 'observed': 41, 'migration': '0042', 'evidence_line': 57}
    return answer_task(root, files, 'Diagnose startup.log against schema.json and migration metadata. Return root_cause, database, expected, observed, migration (lexical string), evidence_line (1-based). Ignore successful cache fallback. Preserve inputs.', answer, 'diagnosis.json')


def log_trace(root):
    records = [{'trace': 'noise', 'level': 'INFO', 'phase': 'health', 'ok': True} for _ in range(45)]
    records += [{'trace': 'A', 'level': 'ERROR', 'code': 'PAYMENT_TIMEOUT', 'service': 'billing'},
                {'trace': 'B', 'level': 'ERROR', 'code': 'ADDRESS_INVALID', 'service': 'shipping'},
                {'trace': 'A', 'level': 'ERROR', 'code': 'ORDER_ABORTED', 'caused_by': 'PAYMENT_TIMEOUT', 'service': 'orders'}]
    files = {'traces.jsonl': ''.join(json.dumps(row) + '\n' for row in records), 'incident.md': 'Investigate trace A only; trace B is a separate customer incident.\n'}
    answer = {'trace': 'A', 'root_cause': 'PAYMENT_TIMEOUT', 'service': 'billing', 'downstream': 'ORDER_ABORTED', 'evidence_line': 46, 'unrelated_trace': 'B'}
    return answer_task(root, files, 'Find the root cause for the incident trace, separating interleaved unrelated errors. Return trace, root_cause, service, downstream, evidence_line (1-based traces.jsonl), unrelated_trace. Preserve inputs.', answer, 'diagnosis.json')


def documents_shipping(root):
    files = {'zones.csv': 'postal_prefix,zone,base_cents\n01,A,500\n02,B,750\n03,C,1100\n',
             'policy.md': '# Shipping\nUse the first two postal-code characters as a lexical prefix.\nZone B adds 120 cents per whole kilogram above 2 kg.\nCount any fractional excess kilogram as a whole kilogram.\nOrders with subtotal at least 10000 cents receive free shipping.\n',
             'order.json': '{"postal_code":"021234","weight_grams":3500,"subtotal_cents":9999}\n'}
    answer = {'postal_prefix': '02', 'zone': 'B', 'base_cents': 750, 'excess_kg': 2, 'shipping_cents': 990, 'free_shipping': False}
    return answer_task(root, files, 'Compute shipping for order.json using zones.csv and policy.md. Return postal_prefix, zone, base_cents, excess_kg, shipping_cents, free_shipping. Preserve inputs.', answer)


def documents_stock(root):
    files = {'stock.json': '[{"sku":"0007","warehouse":"east","on_hand":15,"reserved":4},{"sku":"0007","warehouse":"west","on_hand":9,"reserved":2},{"sku":"0008","warehouse":"east","on_hand":99,"reserved":0}]\n',
             'request.json': '{"sku":"0007","quantity":13,"preferred":"east"}\n'}
    for name, body in files.items():
        write(root, name, body)
    docx(root / 'allocation.docx', ['Allocation rules', 'Available inventory is on_hand minus reserved.', 'Use the preferred warehouse first, then west. Do not exceed availability.', 'If total availability is sufficient, backordered quantity is zero. Preserve lexical SKU identifiers.'])
    answer = {'sku': '0007', 'east_available': 11, 'west_available': 7, 'east_allocated': 11, 'west_allocated': 2, 'backordered': 0}
    return {'spec': 'Allocate request.json using stock.json and allocation.docx. Write answer.json with exactly sku, east_available, west_available, east_allocated, west_allocated, backordered.' + SUFFIX,
            'answer': answer, 'preserved': snapshots(root)}


def documents_tariff(root):
    files = {'tariffs.tsv': 'plan\teffective_date\tmonthly_cents\tincluded_units\toverage_cents\n001\t2026-01-01\t1000\t100\t12\n001\t2026-09-01\t1500\t150\t10\n002\t2026-09-01\t3000\t500\t8\n',
             'policy.md': '# Monthly billing\nChoose the latest tariff effective on the billing date for the exact lexical plan.\nCharge monthly_cents plus max(0, usage-included_units)*overage_cents.\nTax is 900 basis points applied to the final subtotal, rounded half up to an integer cent.\n',
             'usage.json': '{"plan":"001","billing_date":"2026-10-01","units":173}\n'}
    answer = {'plan': '001', 'effective_date': '2026-09-01', 'overage_units': 23, 'subtotal_cents': 1730, 'tax_cents': 156, 'total_cents': 1886}
    return answer_task(root, files, 'Compute the bill from usage.json, tariffs.tsv and policy.md. Return plan, effective_date, overage_units, subtotal_cents, tax_cents, total_cents. Preserve inputs.', answer)


BUILDERS = {'code_location_cache': location_cache, 'code_location_authority': location_authority,
            'code_location_rounding': location_rounding, 'repair_tests_ranges': repair_ranges,
            'repair_tests_config': repair_config, 'repair_tests_durations': repair_durations,
            'batch_changes_imports': batch_imports, 'batch_changes_environment': batch_environment,
            'batch_changes_release': batch_release, 'log_diagnosis_compiler': log_compiler,
            'log_diagnosis_migration': log_migration, 'log_diagnosis_trace': log_trace,
            'document_lookup_shipping': documents_shipping, 'document_lookup_stock': documents_stock,
            'document_lookup_tariff': documents_tariff}


def evaluate_repair(root, expected):
    definition = expected['genericRepair']
    module_spec = importlib.util.spec_from_file_location('evaluated_fixture', root / definition['file'])
    module = importlib.util.module_from_spec(module_spec)
    failures = []
    try:
        module_spec.loader.exec_module(module)
        function = getattr(module, definition['function'])
        for index, case in enumerate(definition['cases']):
            args = copy.deepcopy(case['args'])
            try:
                actual = function(*args)
                if json.dumps(actual, sort_keys=True) != json.dumps(case['expected'], sort_keys=True) or args != case['args']:
                    failures.append({'case': index, 'reason': 'result or input mutation'})
                _poison(actual)
                if args != case['args']:
                    failures.append({'case': index, 'reason': 'returned value aliases an input container'})
            except Exception as exc:
                failures.append({'case': index, 'reason': type(exc).__name__})
    except Exception as exc:
        failures.append({'reason': type(exc).__name__})
    return {'passed': not failures, 'checks': len(definition['cases']), 'failures': failures}


def _poison(value):
    if isinstance(value, dict):
        for child in list(value.values()):
            _poison(child)
        value['__oracle_alias_probe__'] = True
    elif isinstance(value, list):
        for child in list(value):
            _poison(child)
        value.append('__oracle_alias_probe__')
