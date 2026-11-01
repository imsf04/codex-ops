"""On-demand workflow and staged task contracts; discovery has no side effects."""
import copy

CAPABILITIES = [
    {'operation': 'workflows', 'tool': 'ops_workflow', 'description': 'Source investigation, typed documents, acquired evidence and native verification; SDK optional.'},
    {'operation': 'task', 'tool': 'ops_task', 'description': 'Bounded staged file/tree plans and native status/resume/cancel/rollback commands.'},
]


def _directory_schemas():
    path = {'type': 'string', 'minLength': 1, 'description': 'Explicit path relative to the absolute task root; links and credential paths rejected.'}
    single = {'type': 'object', 'properties': {'path': path}, 'required': ['path'], 'additionalProperties': False}
    transfer = {'type': 'object', 'properties': {'path': path, 'to': path}, 'required': ['path', 'to'], 'additionalProperties': False}
    return {**dict.fromkeys(('mkdir', 'rmdir', 'remove_tree'), single),
            **dict.fromkeys(('copy_tree', 'move_tree'), transfer)}


def task(schemas):
    operations = {key: copy.deepcopy(schemas[key]) for key in ('write', 'edit', 'replace', 'copy', 'move', 'remove')}
    operations.update(_directory_schemas())
    return {'status': 'completed', 'effectState': 'none', 'tool': 'ops_task',
            'planArguments': {'root': '<existing-absolute-root>', 'action': 'plan',
                'args': {'stages': [[{'operation': 'mkdir', 'args': {'path': 'output'}}],
                    [{'operation': 'write', 'args': {'path': 'output/result.txt', 'content': 'done'}}]]}},
            'operationSchemas': operations, 'stageContract': '1..16 ordered arrays of1..32 operations; <=64 requested operations in total; repeated paths execute in declared order.',
            'bounds': {'nodes': 128, 'bytes': 8388608, 'fileBytes': 1048576, 'primitiveSteps': 256},
            'lifecycle': {'actions': ['status', 'resume', 'cancel', 'rollback'], 'args': {'id': '<task-id>'}},
            'execution': 'Every action returns nativeExecution argv; run it through exec_command. Planning grants no execution permission.',
            'recovery': 'Inspect status after uncertain effects. Cancel takes effect before the next step; native process termination remains separate.'}


def workflows():
    return {'status': 'completed', 'effectState': 'none', 'operation': 'workflows',
            'tool': 'ops_workflow', 'root': 'Existing absolute workspace directory.',
            'usage': 'For code questions call {root,question}; other workflows use {root,operation,args}. No SDK setup is required.',
            'direct': {'root': '<existing-absolute-root>', 'question': 'Where is retry_delay capped and tested?'},
            'investigateArguments': {'question': '1..2000 characters, at most8000 UTF-8 bytes',
                'anchors': 'Optional array of up to8 literal symbols', 'paths': 'Optional array of1..4 files/directories',
                'focus': ['auto', 'definition', 'references', 'configuration', 'failure'], 'maxBytes': '4096..24576'},
            'recipes': [
                {'when': 'Investigate a question with exact source evidence; add identifiers for opaque language.',
                 'operation': 'investigate', 'args': {'question': 'Where is retry_delay capped?', 'anchors': ['retry_delay']}},
                {'when': 'Search several already acquired observations in one call.',
                 'operation': 'evidence', 'args': {'refs': ['ops://...'], 'query': 'failure'}},
                {'when': 'Save evidence and pending checks for explicit recovery.',
                 'operation': 'working_set', 'args': {'action': 'save', 'sources': [{'ref': 'ops://...'}], 'pending': ['Check final tests']}},
                {'when': 'Resume this chat/root latest automatic source evidence; optional workingSetRef selects an explicit saved set.',
                 'operation': 'working_set', 'args': {'action': 'resume'}},
                {'when': 'Analyze completed or still-running native command chunks.',
                 'operation': 'verify', 'args': {'results': [{'exit_code': 0, 'output': 'tests passed'}]}},
                {'when': 'Find code and read matching source context together.',
                 'operation': 'locate', 'args': {'pattern': 'relevant regex', 'path': '.',
                                               'before': 3, 'after': 8, 'maxMatches': 12, 'maxFiles': 4}},
                {'when': 'Inspect a log file once; log or logRef can replace logPath.',
                 'operation': 'diagnose', 'args': {'logPath': 'build.log', 'maxLocations': 6}},
                {'when': 'Find literal evidence across 1..4 documents or tables.',
                 'operation': 'documents', 'args': {'requests': [
                     {'operation': 'read_table', 'args': {'path': 'data.csv', 'limit': 1000}},
                     {'operation': 'read', 'args': {'files': [{'path': 'notes.md', 'offset': 1, 'limit': 80}]}}
                 ], 'query': 'literal evidence'}},
                {'when': 'Recheck explicit ranges; omit baselineRef on the first call.',
                 'operation': 'incremental', 'args': {'files': [{'path': 'app.py', 'offset': 1, 'limit': 40}],
                                                    'baselineRef': '<previous snapshot ref>'}}],
            'results': 'Unwrap kind=inline.value; retrieve references only for missing evidence. Check coverage/cursors.',
            'sdk': {'operation': 'sdk', 'args': {}, 'purpose': 'Optional callable JS factory and complete argument types.'},
            'native': 'Commands, writes and polling stay native. Prefer native tools for simple known reads or unsupported cases.'}


def describe(operation, schemas):
    return task(schemas) if operation == 'task' else workflows()
