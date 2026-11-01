"""Composable read-only workflows over the existing permissioned file adapter."""
import files
import sdk_workflow
import workflow_diagnostics
import workflow_documents
import workflow_incremental
import investigate
import evidence_index
import working_set
import verification_workflow
from store import error
from workflow_validation import identity, options, root_path

OPERATIONS = ('locate', 'diagnose', 'documents', 'incremental', 'investigate', 'sdk', 'evidence', 'working_set', 'verify')


def _dispatch(root, operation, args, context, invoke, load, save):
    if operation == 'locate':
        return invoke(root, 'search', args)
    if operation == 'diagnose':
        return workflow_diagnostics.run(root, args, invoke, load)
    if operation == 'documents':
        return workflow_documents.run(root, args, invoke, save)
    if operation == 'incremental':
        return workflow_incremental.run(root, args, context, invoke, load, save)
    return _extra(root, operation, args, invoke)


def _extra(root, operation, args, invoke):
    if operation == 'investigate':
        return investigate.run(root, args, invoke)
    options(args, ())
    return sdk_workflow.describe()


def run(root, operation, args, context, invoke=files.run, load=None, save=None):
    if operation not in OPERATIONS:
        return error('UNKNOWN_WORKFLOW', 'Select ' + ', '.join(OPERATIONS))
    try:
        base = root_path(root)
        identity(context)
        if operation in ('evidence', 'working_set', 'verify'):
            return _stateful(base, operation, args, context, invoke, load, save)
        return _dispatch(base, operation, args, context, invoke, load, save)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return error('WORKFLOW_REJECTED', str(exc))


def _stateful(root, operation, args, context, invoke, load, save):
    if operation == 'verify':
        diagnose = lambda base, action, options: _dispatch(base, action, options, context, invoke, load, save)
        return verification_workflow.run(root, args, diagnose)
    handler = {'evidence': evidence_index.run, 'working_set': working_set.run}[operation]
    return handler(root, args, context, invoke, load, save)
