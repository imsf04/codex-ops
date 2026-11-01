"""Native stdio MCP surface. Shell execution stays in Codex's permissioned tool."""
from typing import Any
from pathlib import Path
import os
import sys
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

import files
import runtime_status
import telemetry
import observation_metrics
import result_batch
import catalog
import query_preview
import session_scope
import doctor
import workflow
import workflow_preview
import task_api
import task_preview
import task_cost
import adaptive_budget_ledger
import cost_events
import workflow_entry
from mutations import plan as mutation_plan, summary as mutation_summary
from bridge_context import mcp_context
from store import Store, error

app = MCPServer('codex-ops')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def _owner(ctx):
    if ctx is None:
        return None
    runtime = runtime_status.current().get('managerPid')
    owner = session_scope.from_meta(ctx.request_context.meta, str(runtime) if runtime else None)
    if not owner['session'] and not owner['runtime']:
        owner['runtime'] = 'mcp:' + str(os.getpid())
    return owner


def _scoped_callback(store, callback, ctx):
    with session_scope.bind(_owner(ctx)):
        return callback(store)


def with_store(callback, ctx=None):
    store = None
    try:
        store = Store()
        return _scoped_callback(store, callback, ctx)
    except Exception as exc:
        return error('STORE_ERROR', str(exc))
    finally:
        if store:
            store.close()


@app.tool(annotations=LOCAL)
def ops_capture(value: Any, ctx: Context = None) -> dict:
    """Publish a tool result compactly: keep raw JS value, text this tool's response. Large JSON/text gets an ops:// ref; small values inline. Local 24h/100MiB cache, max 10MiB each. Never re-executes the source."""
    return with_store(lambda store: observation_metrics.reference(store.capture(value), _context(ctx, 'ops_capture')), ctx)


def _context(ctx, tool):
    return mcp_context(ctx.request_context.meta if ctx is not None else None, tool)


@app.tool(annotations=LOCAL)
def ops_result(ref: str = '', view: str = 'items', path: str = '', fields: list[str] | None = None,
               query: str = '', offset: int = 0, limit: int = 40, max_bytes: int = 6000,
               action: str = 'page', requests: list[dict] | None = None, ctx: Context = None) -> dict:
    """Query cached observations without rerunning sources. views: outline pointers; find literal matches; items path/fields/filter; count matching records; group by one scalar field; raw exact text/JSON. offset counts view items (raw Unicode characters), limit1..200 (raw ignored), max_bytes512..16000. action=batch with1..8 requests queries multiple refs/views under one total max_bytes; omit top-level ref. Each request uses the same page options. Follow nextOffset and scanComplete; complete covers saved view only. action=release frees a reference."""
    if action == 'batch':
        if ref:
            return error('INVALID_ARGUMENT', 'Batch uses requests instead of top-level ref')
        return with_store(lambda store: result_batch.run(store, requests, max_bytes), ctx)
    if requests is not None:
        return error('INVALID_ARGUMENT', 'requests requires action=batch')
    options = [view, path, fields, query, offset, limit, max_bytes, action]
    return with_store(lambda store: observation_metrics.retrieval(
        store.result(ref, *options), options, _context(ctx, 'ops_result').get('session')), ctx)


@app.tool(annotations=READ)
def ops_files(root: str, operation: str, args: dict, ctx: Context = None) -> dict:
    """Read-only files under absolute root. search: {pattern,path:'.',before:3,after:3,maxMatches:20,maxFiles:4} returns grep hits plus merged context in one call; snapshots non-atomic. read: {files:[{path,offset:1,limit:200}]} max32. batch: {requests:[{operation,args}]}1..4 independent native read ops. Also grep/glob/stat/diff/inspect/read_table/read_docx/read_pdf. ops_catalog supplies exact schemas/examples; preserve coverage and continuations."""
    context = _context(ctx, 'ops_files.' + operation)
    with cost_events.scope(context.get('session'), root):
        value = files.run(root, operation, args)
    return with_store(lambda store: observation_metrics.reference(
        query_preview.capture(store, value, operation), context), ctx)


@app.tool(annotations=READ)
def ops_catalog(operation: str = '') -> dict:
    """Discover supported operations without execution. Empty operation returns a thin capability list; select one exact operation for its argument JSON Schema, examples, limits and recovery guidance. Use before an unfamiliar ops_files or ops_plan operation. Does not load or replace native Codex tools."""
    return catalog.describe(operation)


def _plan_receipt(store, value, context):
    _require_plan_identity()
    receipt = store.capture(value, scope='mutation-plan', force=True)
    if receipt.get('kind') != 'reference':
        return receipt
    overview = mutation_summary(value)
    overview['items'] = overview['items'][:8]
    overview['previewOnly'] = len(value['items']) > 8
    receipt['preview'] = overview
    receipt['nativeExecution'] = {'executable': sys.executable,
        'args': [str(Path(__file__).parent / 'mutations/__main__.py'), 'apply', '--plan-ref', receipt['ref']],
        'permission': 'Run through Codex exec_command with its normal sandbox and approval policy'}
    return observation_metrics.reference(receipt, context)


@app.tool(annotations=LOCAL)
def ops_plan(root: str, operations: list[dict], ctx: Context = None) -> dict:
    """Plan 1..32 disjoint file changes without modifying workspace files. Each {operation,args}: write {path,content}; edit {path,edits:[{oldText,newText}]}; replace {path,oldText,newText,expectedCount}; copy/move {path,to}; remove {path}. Root must be absolute; parents exist; files <=1MiB; destination absent. Saves a CAS plan reference and returns native CLI argv. Apply/resume/rollback only through Codex exec_command; a plan grants no execution permission. See references/mutations.md."""
    try:
        value = mutation_plan(root, operations)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return error('PLAN_REJECTED', str(exc))
    return with_store(lambda store: _plan_receipt(store, value, _context(ctx, 'ops_plan')), ctx)


@app.tool(annotations=READ)
def ops_stats(origin: str = 'production', window: str = 'all', check_runtime: bool = False,
              ctx: Context = None, since: str | None = None, until: str | None = None,
              turn_id: str | None = None) -> dict:
    """Inspect runtime, actual chat usage and separately versioned workflow/worker measurements. origin=production|validation; since/until accept timezone-aware ISO times, turn_id selects a native turn. Workflow completion, useful evidence and labelled opportunities differ; unknown adoption stays unknown. window=all|hour|day|week selects presentation-byte buckets, not task usage. Bytes, tokens, outer/native/worker calls are separate measures; counters alone do not establish savings."""
    return with_store(lambda store: {**store.stats(), 'runtimeBridge': runtime_status.current(),
                                      'installation': doctor.report(check_runtime),
                                      'presentationTotals': telemetry.snapshot(origin, window=window),
                                      'taskCosts': task_cost.report(_context(ctx, 'ops_stats').get('session'),
                                            since=since, until=until, turn_id=turn_id, origin=origin)}, ctx)


def _workflow(store, root, operation, args, ctx):
    owner = session_scope.CURRENT.get() or {}
    args = _workflow_budget(operation, args, owner)
    context = _context(ctx, 'ops_workflow.' + operation)
    with cost_events.scope(context.get('session'), root):
        value = workflow_entry.run(store, root, owner, operation, args)
        observation_metrics.workflow(value, operation, context, root)
    receipt = workflow_preview.capture(store, value, operation)
    return observation_metrics.reference(receipt, context)


def _workflow_budget(operation, args, owner):
    if operation != 'investigate' or not isinstance(args, dict):
        return args
    if 'maxBytes' in args:
        return args
    budget = adaptive_budget_ledger.budget(owner.get('session'))
    return {**args, 'maxBytes': budget['recommendedBytes']}


@app.tool(annotations=LOCAL)
def ops_workflow(root: str, operation: str = 'investigate', args: dict | None = None,
                 ctx: Context = None, question: str | None = None) -> dict:
    """Investigate code with root (absolute) and question; defaults find source evidence, relevant tests/config and save it for recovery. Advanced args: anchors:[symbols], paths:[files/directories], focus:auto|definition|references|configuration|failure, maxBytes:4096..24576. Other operations use args: documents={requests:[{operation:'read',args:{files:[{path:'policy.docx'}]}}]} routes file formats; diagnose={logPath:'build.log'}; evidence={refs:[...],query:'terms'}; working_set={action:'resume'} recovers this chat/root's latest acquired source evidence and rechecks revisions. verify={results:[nativeChunks]} analyzes existing results. ops_catalog('workflows') has advanced contracts. Read delivered evidence; commands and writes stay native."""
    try:
        options = workflow_entry.arguments(operation, args, question)
    except ValueError as exc:
        return error('WORKFLOW_REJECTED', str(exc))
    return with_store(lambda store: _workflow(store, root, operation, options, ctx), ctx)


def _task_plan(store, root, args, ctx):
    _require_plan_identity()
    if set(args) != {'stages'}:
        raise ValueError('Task plan accepts stages only')
    value = task_api.plan(root, args['stages'], owner=session_scope.CURRENT.get())
    return task_preview.capture(store, value)


def _require_plan_identity():
    owner = session_scope.CURRENT.get()
    if owner is not None and not owner.get('session'):
        raise ValueError('Executable reference plans require native chat identity; no execution was started.')


def _task(store, root, action, args, ctx):
    try:
        if action == 'plan':
            return _task_plan(store, root, args, ctx)
        if set(args) != {'id'}:
            raise ValueError('Task lifecycle commands require id only')
        return {'kind': 'native-command', 'action': action,
                'nativeExecution': task_api.command(action, root, args['id'])}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return error('TASK_REJECTED', str(exc))


@app.tool(annotations=LOCAL)
def ops_task(root: str, action: str, args: dict, ctx: Context = None) -> dict:
    """Plan or inspect native task commands; MCP never executes workspace changes. plan args={stages:[[{operation,args}],...]}: max16 stages/64 requested ops/256 primitive steps, explicit bounded files/trees. ops_catalog('task') gives exact schemas/examples. Other actions status/resume/cancel/rollback args={id}. Returns nativeExecution argv for exec_command with current permissions. Cancellation is cooperative between steps; uncertain effects require status inspection before resume or rollback."""
    return with_store(lambda store: _task(store, root, action, args, ctx), ctx)


if __name__ == '__main__':
    app.run()
