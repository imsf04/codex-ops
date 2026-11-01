"""On-demand workflow and staged task contracts; discovery has no side effects."""
import copy

CAPABILITIES = [
    {'operation': 'workflows', 'tool': 'ops_workflow', 'description': 'Composable location, diagnostic, document and incremental evidence with callable SDK.'},
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
            'usage': 'Call directly with {root,operation,args}; no SDK setup is required.',
            'recipes': [
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
