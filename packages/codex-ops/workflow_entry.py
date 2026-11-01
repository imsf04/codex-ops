"""Common workflow entry with automatic, permission-scoped evidence recovery."""
import files
import cost_events
import session_scope
import workflow
import workflow_memory
from store import ReferenceUnavailable, error
from workflow_validation import require, root_path


def arguments(operation, args, question):
    result = {} if args is None else args
    require(isinstance(result, dict), 'args must be an object')
    if question is None:
        return result
    require(operation == 'investigate', 'question is supported by investigate only')
    require('question' not in result, 'Supply question once, at the top level or inside args')
    return {**result, 'question': question}


def _recovery(store, root, owner, operation, args):
    if operation != 'working_set' or args.get('action') != 'resume':
        return args
    if 'workingSetRef' in args:
        return args
    return {**args, 'workingSetRef': workflow_memory.latest(store, root, owner)}


def _snapshot(store, value):
    receipt = store.capture(value, scope='workflow-snapshot', force=True)
    require(receipt.get('kind') == 'reference', 'Snapshot could not be saved; narrow the evidence')
    return receipt['ref']


def _execute(store, root, owner, operation, args, invoke):
    return workflow.run(root, operation, args, session_scope.identity(owner), invoke=invoke,
                        load=store.get, save=lambda value: _snapshot(store, value))


def _investigate(store, root, owner, args, invoke):
    reused = workflow_memory.reuse(store, root, owner, args, invoke)
    if reused is not None:
        cost_events.record('automatic', 'working_set', outcome='completed', evidence='present', reused=True)
        return reused
    value = _execute(store, root, owner, 'investigate', args, invoke)
    if value.get('evidenceState') != 'collected':
        return value
    memory = workflow_memory.remember(store, root, owner, args, value)
    if memory['state'] == 'saved':
        cost_events.record('automatic', 'working_set.save', outcome='completed', evidence='present')
    return {**value, 'workingSet': memory}


def run(store, root, owner, operation, args, invoke=files.run):
    try:
        root = root_path(root)
        require(isinstance(args, dict), 'args must be an object')
        args = _recovery(store, root, owner, operation, args)
        if operation == 'investigate':
            return _investigate(store, root, owner, args, invoke)
        return _execute(store, root, owner, operation, args, invoke)
    except (ValueError, OSError, KeyError, TypeError, ReferenceUnavailable) as exc:
        return error('WORKFLOW_REJECTED', str(exc))
