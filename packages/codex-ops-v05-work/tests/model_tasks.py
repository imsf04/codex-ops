"""Controlled task fixtures with independent, file-based outcome checks."""
import csv
import hashlib
import json
from pathlib import Path
import zipfile

TASKS = ('code_location', 'repair_tests', 'batch_changes', 'log_diagnosis', 'document_lookup')
SUFFIX = ('\nUse the available tools. Work only in this fixture directory, with no downloads or network requests. '
          'Preserve input files except the changes explicitly requested. Finish with a short report.')


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


def snapshots(root):
    return {str(path.relative_to(root)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def code_location(root):
    modules = {
        'src/network/backoff.py': '''"""HTTP retry scheduling, independent from request timeouts."""
BASE_DELAY_MS = 250
MAX_RETRY_DELAY_MS = 8000

def retry_delay(status, attempt):
    if status != 429:
        return None
    return min(BASE_DELAY_MS * 2 ** attempt, MAX_RETRY_DELAY_MS)
''',
        'src/network/client.py': '''from .backoff import retry_delay

def request_options(status, attempt):
    return {"timeout_ms": 30000, "wait_ms": retry_delay(status, attempt)}
''',
        'src/storage/retry.py': '''MAX_RETRY_DELAY_MS = 2000

def retry_delay(reason, attempt):
    return min(100 * (attempt + 1), MAX_RETRY_DELAY_MS) if reason == "locked" else None
''',
        'src/jobs/scheduling.py': '''def retry_delay(status, attempt):
    return 60 * attempt if status == "queued" else 0
''',
        'tests/test_backoff.py': '''from src.network.backoff import retry_delay

def test_rate_limit_ceiling():
    assert retry_delay(429, 20) == 8000

def test_other_status():
    assert retry_delay(503, 1) is None
''',
        'tests/test_storage_retry.py': '''from src.storage.retry import retry_delay

def test_lock_retry():
    assert retry_delay("locked", 100) == 2000
''',
        'docs/request-timeouts.md': 'HTTP request timeout is 30000 ms. It is not the retry scheduling delay.\n',
        'docs/jobs.md': 'Queued jobs use minute-based rescheduling; this is separate from HTTP rate limiting.\n'}
    for path, body in modules.items():
        write(root, path, body)
    expected = {'path': 'src/network/backoff.py', 'symbol': 'retry_delay', 'line': 5,
                'cap_ms': 8000, 'test_path': 'tests/test_backoff.py', 'test_symbol': 'test_rate_limit_ceiling'}
    spec = ('Find the function that caps retry delay specifically for HTTP 429, and the regression that verifies its ceiling. '
            'Do not change source. Write answer.json with exactly path (relative forward-slash path), symbol, line '
            '(1-based function definition), cap_ms, test_path and test_symbol.')
    return {'spec': spec + SUFFIX, 'answer': expected, 'preserved': snapshots(root)}


def batch_changes(root):
    initial = {}
    for name in ('api', 'worker', 'events', 'billing', 'search', 'scheduler'):
        initial[f'config/{name}.toml'] = f'name = "{name}"\n[retry]\ntimeout_ms = 3000\nattempts = 3\n[database]\ntimeout_ms = 9000\n'
    initial.update({'docs/oncall-draft.md': '# On-call\nEscalate persistent failures to the service owner.\n',
                    'docs/deprecated.txt': 'Retired workflow.\n', 'notes.txt': 'Keep this note byte-for-byte.\n'})
    for name, body in initial.items():
        write(root, name, body)
    preserved = snapshots(root)
    expected = {}
    for name in ('api', 'worker', 'events'):
        path = f'config/{name}.toml'
        expected[path] = initial[path].replace('timeout_ms = 3000', 'timeout_ms = 8000')
        preserved.pop(path)
    expected['docs/oncall.md'] = initial['docs/oncall-draft.md']
    expected['docs/migration.txt'] = 'Retry timeout updated for api, worker, events.\n'
    removed = ['docs/oncall-draft.md', 'docs/deprecated.txt']
    for path in removed:
        preserved.pop(path)
    spec = ('Update only retry.timeout_ms from 3000 to 8000 in config/api.toml, config/worker.toml, and config/events.toml. '
            'Keep database settings and other configs unchanged. Rename docs/oncall-draft.md to docs/oncall.md preserving its bytes. '
            'Remove docs/deprecated.txt. Create docs/migration.txt containing exactly "Retry timeout updated for api, worker, events." '
            'followed by one newline. Verify the completed batch.')
    return {'spec': spec + SUFFIX, 'files': expected, 'removed': removed, 'preserved': preserved}


def log_diagnosis(root):
    lines = ['2026-10-29T01:00:00Z INFO build_id=op-431 phase=load-config']
    for index in range(90):
        lines.append(f'2026-10-29T01:00:{index % 60:02}Z INFO check=asset-{index:03} status=passed bytes={128 + index * 17}')
    lines += ['2026-10-29T01:02:00Z WARN check=cache status=miss fallback=local success=true',
              '2026-10-29T01:02:01Z ERROR code=INVALID_REGION file=config/api.toml key=region observed=SGP expected=SG',
              '2026-10-29T01:02:01Z ERROR code=VALIDATION_ABORTED caused_by=INVALID_REGION',
              '2026-10-29T01:02:02Z ERROR code=BUILD_FAILED exit_code=1']
    write(root, 'build.log', '\n'.join(lines) + '\n')
    write(root, 'config/api.toml', 'region = "SGP"\nservice = "orders"\n')
    write(root, 'docs/regions.md', 'Deployment regions use SG, CN and US. Singapore is SG; SGP is not accepted.\n')
    expected = {'root_cause': 'INVALID_REGION', 'file': 'config/api.toml', 'key': 'region',
                'observed': 'SGP', 'expected': 'SG', 'evidence_line': 93}
    spec = ('Diagnose the primary cause of the failed build from build.log and the supporting configuration/docs. '
            'Distinguish the cause from downstream BUILD_FAILED/VALIDATION_ABORTED. Do not modify the inputs. '
            'Write diagnosis.json with exactly root_cause (error code), file, key, observed, expected, evidence_line '
            '(1-based line in build.log).')
    return {'spec': spec + SUFFIX, 'answer': expected, 'answerFile': 'diagnosis.json', 'preserved': snapshots(root)}


def docx(path, paragraphs):
    body = ''.join('<w:p><w:r><w:t>' + text + '</w:t></w:r></w:p>' for text in paragraphs)
    parts = {'[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
             '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
             'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>'}
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value.encode())


def document_lookup(root):
    with (root / 'prices.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['product_code', 'region', 'effective_date', 'currency', 'unit_price_cents'])
        for number in range(1, 61):
            for region, currency in [('CN', 'CNY'), ('SG', 'SGD'), ('US', 'USD')]:
                for date, delta in [('2026-06-01', 0), ('2026-09-01', 100)]:
                    amount = 1199 + delta if number == 42 and region == 'SG' else 400 + number * 17 + delta
                    writer.writerow([f'{number:04}', region, date, currency, amount])
    docx(root / 'policy.docx', ['Bulk pricing', 'Product codes are lexical strings; preserve leading zeros.',
          'Select the latest effective_date no later than the quote date for the exact product_code and region.',
          'Orders of at least 10 units receive a discount of 1250 basis points (12.5 percent). Smaller orders receive no discount.',
          'Compute the entire order subtotal in integer cents, then apply the discount once. Round half up to one integer cent.'])
    expected = {'product_code': '0042', 'currency': 'SGD', 'effective_date': '2026-09-01',
                'unit_price_cents': 1299, 'minimum_units': 10, 'discount_bps': 1250,
                'quantity': 12, 'quote_cents': 13640, 'policy_section': 'Bulk pricing'}
    spec = ('Use prices.csv and policy.docx to quote product_code "0042", region SG, quantity 12, on 2026-10-01. '
            'Preserve input files. Write answer.json with exactly product_code, currency, effective_date, unit_price_cents, '
            'minimum_units, discount_bps, quantity, quote_cents and policy_section. Use the effective-date and rounding rules in the document.')
    return {'spec': spec + SUFFIX, 'answer': expected, 'preserved': snapshots(root)}


BUILDERS = {'code_location': code_location, 'batch_changes': batch_changes,
            'log_diagnosis': log_diagnosis, 'document_lookup': document_lookup}


def prepare_task(name, root):
    if name == 'repair_tests':
        from run_model_benchmark import prepare, SPEC
        prepare(root)
        preserved = snapshots(root)
        preserved.pop('ledger.py')
        preserved.pop('test_ledger.py')  # The task explicitly permits focused new regressions.
        return {'spec': SPEC, 'preserved': preserved, 'repair': True}
    root.mkdir(parents=True)
    return BUILDERS[name](root)


def preserved_failures(root, expected):
    failures = []
    for name, digest in expected.items():
        path = root / name
        try:
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                failures.append({'file': name, 'reason': 'input changed or disappeared'})
        except OSError as exc:
            failures.append({'file': name, 'reason': 'input unreadable: ' + type(exc).__name__})
    return failures


def evaluate_task(name, root, expected):
    failures = preserved_failures(root, expected['preserved'])
    checks = len(expected['preserved'])
    if name == 'repair_tests':
        from run_model_benchmark import evaluate
        result = evaluate(root)
        return {**result, 'passed': result['passed'] and not failures, 'inputPreservationFailures': failures}
    if 'answer' in expected:
        answer = root / expected.get('answerFile', 'answer.json')
        try:
            actual = json.loads(answer.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            actual = {'error': type(exc).__name__}
        checks += len(expected['answer'])
        if actual != expected['answer']:
            failures.append({'reason': 'answer differs from independent oracle', 'observed': actual})
    else:
        for filename, content in expected['files'].items():
            checks += 1
            path = root / filename
            try:
                if not path.is_file() or path.read_bytes() != content.encode():
                    failures.append({'file': filename, 'reason': 'target bytes differ'})
            except OSError as exc:
                failures.append({'file': filename, 'reason': 'target unreadable: ' + type(exc).__name__})
        for filename in expected['removed']:
            checks += 1
            if (root / filename).exists():
                failures.append({'file': filename, 'reason': 'expected absent'})
    return {'passed': not failures, 'checks': checks, 'failures': failures}


def solve_for_self_test(name, root, expected):
    if name == 'repair_tests':
        import inspect
        from run_model_benchmark import oracle
        write(root, 'ledger.py', inspect.getsource(oracle).replace('def oracle(', 'def summarize('))
    elif 'answer' in expected:
        write(root, expected.get('answerFile', 'answer.json'), json.dumps(expected['answer']))
    else:
        for filename, content in expected['files'].items():
            write(root, filename, content)
        for filename in expected['removed']:
            (root / filename).unlink()
