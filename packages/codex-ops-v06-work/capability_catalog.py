"""On-demand workflow and staged task contracts; discovery has no side effects."""
import copy
import sdk_workflow

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
    return {**sdk_workflow.describe(), 'operation': 'workflows', 'tool': 'ops_workflow',
            'discovery': 'The TypeScript declarations are the argument contract; sdk operation returns the same callable JavaScript factory.'}


def describe(operation, schemas):
    return task(schemas) if operation == 'task' else workflows()
