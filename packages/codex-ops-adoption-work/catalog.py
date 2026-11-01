"""On-demand adapter contracts; describing a capability never runs it."""
import copy
import capability_catalog
from store import error
from query_workflow import BOUNDS


def obj(properties, required=()):
    return {'type': 'object', 'properties': properties, 'required': list(required), 'additionalProperties': False}


def integer(low=0, high=None, default=None):
    result = {'type': 'integer', 'minimum': low}
    if high is not None:
        result['maximum'] = high
    if default is not None:
        result['default'] = default
    return result


def array(items, low=0, high=None):
    result = {'type': 'array', 'items': items, 'minItems': low}
    if high is not None:
        result['maxItems'] = high
    return result


STRING = {'type': 'string'}
NONEMPTY = {'type': 'string', 'minLength': 1}
BOOLEAN = {'type': 'boolean'}
PATH = {**NONEMPTY, 'description': 'Relative to the explicit absolute root; cannot leave it; links and credential paths are rejected.'}
PAGE = {'offset': integer(), 'limit': integer(1, 10000, 100)}
CURSOR = {**STRING, 'description': 'Native continuation; preserve original query options. SEARCH_STALE requires a new search.'}
RANGE = obj({'path': PATH, 'offset': integer(1, default=1), 'limit': integer(1, 10000, 200)}, ['path'])
READ_SCHEMAS = {
    'read': obj({'files': array(RANGE, 1, 32)}, ['files']),
    'inspect': obj({'path': PATH, 'offset': integer(0, default=1), 'limit': integer(1, 10000, 200),
                    'view': {'type': 'string', 'enum': ['text', 'hex'], 'default': 'text'},
                    'encoding': {'type': 'string', 'const': 'utf-8'}}, ['path']),
    'grep': obj({'path': PATH, 'pattern': STRING, 'glob': array(STRING), 'caseInsensitive': BOOLEAN,
                 'lineNumbers': BOOLEAN, 'beforeContext': integer(0, 32), 'afterContext': integer(0, 32),
                 'multiline': BOOLEAN, 'exactTotal': BOOLEAN, **PAGE, 'continuation': CURSOR,
                 'outputMode': {'type': 'string', 'enum': ['content', 'files_with_matches', 'count', 'summary']}}, ['pattern']),
    'glob': obj({'path': PATH, 'pattern': array(STRING, 1), **PAGE, 'continuation': CURSOR,
                 'outputMode': {'type': 'string', 'enum': ['paths', 'details']},
                 'sort': {'type': 'string', 'enum': ['path', 'modified']}}, ['pattern']),
    'stat': obj({'path': PATH}, ['path']),
    'diff': obj({'path': PATH, 'content': STRING, 'offset': integer(), 'limit': integer(1, 1000, 100)}, ['path', 'content']),
    'read_table': obj({'path': PATH, 'format': {'type': 'string', 'enum': ['csv', 'tsv']},
                       'encoding': {'type': 'string', 'enum': ['utf-8', 'utf-16le', 'utf-16be']},
                       'header': BOOLEAN, 'offset': integer(1, 100000, 1), 'limit': integer(1, 1000, 200)}, ['path']),
    'read_docx': obj({'path': PATH, 'offset': integer(1, 100000, 1), 'limit': integer(1, 1000, 200)}, ['path']),
    'read_pdf': obj({'path': PATH, 'offset': integer(1, 32, 1), 'limit': integer(1, 32, 10)}, ['path']),
}
SCHEMAS = {**READ_SCHEMAS,
    'batch': obj({'requests': array({'oneOf': [obj({'operation': {'const': name}, 'args': schema}, ['operation', 'args'])
                                             for name, schema in READ_SCHEMAS.items()]}, 1, 4)}, ['requests']),
    'search': obj({'path': {**PATH, 'maxLength': 4096}, 'pattern': {**NONEMPTY, 'maxLength': 4096},
                   'glob': array({**NONEMPTY, 'maxLength': 512}, high=32), 'caseInsensitive': BOOLEAN,
                   **{key: integer(low, high, default) for key, (low, high, default) in BOUNDS.items()}}, ['pattern']),
    'write': obj({'path': PATH, 'content': STRING}, ['path', 'content']),
    'edit': obj({'path': PATH, 'edits': array(obj({'oldText': NONEMPTY, 'newText': STRING}, ['oldText', 'newText']), 1, 100)}, ['path', 'edits']),
    'replace': obj({'path': PATH, 'oldText': NONEMPTY, 'newText': STRING, 'expectedCount': integer(1)}, ['path', 'oldText', 'newText', 'expectedCount']),
    'copy': obj({'path': PATH, 'to': PATH}, ['path', 'to']),
    'move': obj({'path': PATH, 'to': PATH}, ['path', 'to']),
    'remove': obj({'path': PATH}, ['path']),
}
DESCRIPTIONS = {
    'read': 'Read 1–32 explicit UTF-8 line ranges.', 'inspect': 'Inspect UTF-8 lines or bounded hexadecimal byte rows.',
    'grep': 'Search a Rust regular expression with honest scan/page coverage.', 'glob': 'Find eligible files using a positive glob array.',
    'stat': 'Observe file existence and revision.', 'diff': 'Compare proposed complete text without writing.',
    'read_table': 'Read lexical CSV/TSV cells without type coercion.', 'read_docx': 'Read supported DOCX main-body paragraphs.',
    'read_pdf': 'Read restricted PDF text-layer content order; no OCR.', 'batch': 'Run 1–4 independent read requests concurrently.',
    'search': 'Search and read merged matching-line context in one bounded workflow.',
    'write': 'Plan UTF-8 file creation or replacement.', 'edit': 'Plan unique nonoverlapping literal edits.',
    'replace': 'Plan a literal replacement with an exact expected match count.',
    'copy': 'Plan copying a regular file to an absent destination.', 'move': 'Plan moving a regular file to an absent destination.',
    'remove': 'Plan removal of one regular file with recovery snapshot.',
}
EXAMPLES = {
    'read': {'files': [{'path': 'src/main.py', 'offset': 1, 'limit': 80}]},
    'inspect': {'path': 'sample.bin', 'view': 'hex', 'offset': 1, 'limit': 8},
    'grep': {'path': '.', 'pattern': 'TODO|FIXME', 'glob': ['**/*.py'], 'limit': 20},
    'glob': {'path': '.', 'pattern': ['**/*.py', '!vendor/**'], 'limit': 50},
    'stat': {'path': 'src/main.py'}, 'diff': {'path': 'src/main.py', 'content': 'proposed content\n'},
    'read_table': {'path': 'data.csv', 'offset': 1, 'limit': 50},
    'read_docx': {'path': 'report.docx', 'offset': 1, 'limit': 30},
    'read_pdf': {'path': 'report.pdf', 'offset': 1, 'limit': 5},
    'batch': {'requests': [{'operation': 'stat', 'args': {'path': 'src/main.py'}},
                           {'operation': 'grep', 'args': {'pattern': 'TODO', 'limit': 10}}]},
    'search': {'path': 'src', 'pattern': 'def start', 'glob': ['**/*.py'], 'maxMatches': 20, 'before': 2, 'after': 5},
    'write': {'path': 'notes.txt', 'content': 'updated\n'},
    'edit': {'path': 'src/main.py', 'edits': [{'oldText': 'timeout = 10', 'newText': 'timeout = 20'}]},
    'replace': {'path': 'notes.txt', 'oldText': 'old', 'newText': 'new', 'expectedCount': 2},
    'copy': {'path': 'notes.txt', 'to': 'notes-copy.txt'}, 'move': {'path': 'notes.txt', 'to': 'archive.txt'},
    'remove': {'path': 'obsolete.txt'},
}
MUTATIONS = frozenset(('write', 'edit', 'replace', 'copy', 'move', 'remove'))


def _route(operation):
    return 'ops_plan' if operation in MUTATIONS else 'ops_files'


def _example(operation):
    args = copy.deepcopy(EXAMPLES[operation])
    if operation in MUTATIONS:
        return {'root': '<existing-absolute-root>', 'operations': [{'operation': operation, 'args': args}]}
    return {'root': '<existing-absolute-root>', 'operation': operation, 'args': args}


def _contracts(operation):
    if operation in MUTATIONS:
        return ['Plans never modify workspace files or grant execution authority; use returned nativeExecution through exec_command.',
                '1–32 disjoint explicit-file operations; 1 MiB per file, 8 MiB per plan; existing parents; absent copy/move destination.',
                'After uncertainty inspect journal status, then explicitly resume or rollback; do not repeat apply.']
    if operation == 'search':
        return ['At most 64 search matches, 8 files and 32 merged ranges; shared 45-second deadline.',
                'Search/read are not an atomic snapshot; matched-line changes are reported, unrelated file changes cannot be inferred.',
                'Check search.scanComplete/search.nextOffset, omittedMatches/omittedRanges and matchChecks before concluding absence.']
    return ['Root is an existing absolute directory; native path, link and credential checks remain authoritative.',
            'Check per-result error, scanComplete/pageComplete, pending and continuation; a returned page is not the complete source.',
            'Document readers expose bounded scopes; unsupported encodings/formats are errors, not empty documents.']


def _native(operation=''):
    if not isinstance(operation, str):
        return error('UNKNOWN_OPERATION', 'Select an operation from ops_catalog()')
    if not operation:
        return {'status': 'completed', 'effectState': 'none', 'capabilities': [
            {'operation': name, 'tool': _route(name), 'description': description} for name, description in DESCRIPTIONS.items()] + capability_catalog.CAPABILITIES,
            'nextAction': 'Select one operation to obtain its args JSON Schema and example; discovery executes nothing.'}
    if operation not in SCHEMAS:
        return error('UNKNOWN_OPERATION', 'Select an operation from ops_catalog()')
    return {'status': 'completed', 'effectState': 'none', 'operation': operation, 'tool': _route(operation),
            'description': DESCRIPTIONS[operation], 'argsSchema': copy.deepcopy(SCHEMAS[operation]),
            'example': _example(operation), 'contracts': _contracts(operation),
            'schemaScope': 'Codex Ops adapter arguments; native worker performs remaining semantic checks'}


def describe(operation=''):
    if isinstance(operation, str) and operation in ('workflows', 'task'):
        return capability_catalog.describe(operation, SCHEMAS)
    return _native(operation)
