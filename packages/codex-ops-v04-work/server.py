"""Native stdio MCP surface. Shell execution stays in Codex's permissioned tool."""
from typing import Any
from pathlib import Path
import sys
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

import files
import runtime_status
import telemetry
import observation_metrics
from mutations import plan as mutation_plan, summary as mutation_summary
from bridge_context import mcp_context
from store import Store, error

app = MCPServer('codex-ops')
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)


def with_store(callback):
    store = None
    try:
        store = Store()
        return callback(store)
    except Exception as exc:
        return error('STORE_ERROR', str(exc))
    finally:
        if store:
            store.close()


@app.tool(annotations=LOCAL)
def ops_capture(value: Any, ctx: Context = None) -> dict:
    """Publish a tool result compactly: keep raw JS value, text this tool's response. Large JSON/text gets an ops:// ref; small values inline. Local 24h/100MiB cache, max 10MiB each. Never re-executes the source."""
    return with_store(lambda store: observation_metrics.reference(store.capture(value), _context(ctx, 'ops_capture')))


def _context(ctx, tool):
    return mcp_context(ctx.request_context.meta if ctx is not None else None, tool)


@app.tool(annotations=LOCAL)
def ops_result(ref: str, view: str = 'items', path: str = '', fields: list[str] | None = None,
               query: str = '', offset: int = 0, limit: int = 40, max_bytes: int = 6000,
               action: str = 'page') -> dict:
    """Retrieve/release ops:// observations. outline lists child JSON pointers; find locates literal query across strings with pointer+line. items selects path, fields and literal query; offset counts matches, limit 1..200. raw returns exact original text/JSON with Unicode-character offset; limit ignored. max_bytes 512..16000 bounds every page. Follow nextOffset; complete covers saved view only; find.scanComplete covers its bounded scan."""
    options = [view, path, fields, query, offset, limit, max_bytes, action]
    return with_store(lambda store: observation_metrics.retrieval(
        store.result(ref, *options), options))


@app.tool(annotations=READ)
def ops_files(root: str, operation: str, args: dict, ctx: Context = None) -> dict:
    """Read-only Rust worker under absolute root. read: {files:[{path,offset:1,limit:200}]} (max32); batch: {requests:[{operation,args}]} (1-4, ordered, no nested batch). Also grep/glob/stat/diff/inspect/read_table/read_docx/read_pdf; see skill references/files.md for bounded format contracts. Preserves per-result errors, coverage and continuations; no writes."""
    value = files.run(root, operation, args)
    return with_store(lambda store: observation_metrics.reference(
        store.capture(value), _context(ctx, 'ops_files.' + operation)))


def _plan_receipt(store, value, context):
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
    return with_store(lambda store: _plan_receipt(store, value, _context(ctx, 'ops_plan')))


@app.tool(annotations=READ)
def ops_stats(origin: str = 'production') -> dict:
    """Inspect cache, live bridge and persisted emitted-text statistics. origin=production|validation separates daily use from tests. By-channel/reason bytes include explicit retrieval separately; no payloads, token or net-context claims."""
    return with_store(lambda store: {**store.stats(), 'runtimeBridge': runtime_status.current(),
                                      'presentationTotals': telemetry.snapshot(origin)})


if __name__ == '__main__':
    app.run()
