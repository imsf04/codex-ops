"""Composable read-only workflows over the existing permissioned file adapter."""
import files
import sdk_workflow
import workflow_diagnostics
import workflow_documents
import workflow_incremental
from store import error
from workflow_validation import identity, options, root_path

OPERATIONS = ('locate', 'diagnose', 'documents', 'incremental', 'sdk')


def _dispatch(root, operation, args, context, invoke, load, save):
    if operation == 'locate':
        return invoke(root, 'search', args)
    if operation == 'diagnose':
        return workflow_diagnostics.run(root, args, invoke, load)
    if operation == 'documents':
        return workflow_documents.run(root, args, invoke, save)
    if operation == 'incremental':
        return workflow_incremental.run(root, args, context, invoke, load, save)
    options(args, ())
    return sdk_workflow.describe()


def run(root, operation, args, context, invoke=files.run, load=None, save=None):
    if operation not in OPERATIONS:
        return error('UNKNOWN_WORKFLOW', 'Select locate, diagnose, documents, incremental or sdk')
    try:
        base = root_path(root)
        identity(context)
        return _dispatch(base, operation, args, context, invoke, load, save)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return error('WORKFLOW_REJECTED', str(exc))
