"""PostToolUse presentation only. Fail open; never block/rewrite tool execution."""
import json
import sys

from reducers import encode, has_media
from store import Store, THRESHOLD
import shell_receipt
import runtime_status
import observation_metrics

GUIDANCE = ('Codex Ops: keep full tool values inside functions.exec. For large results, '
            'compute/filter first, then text(await tools.mcp__codex_ops__ops_capture({value: result})); '
            'discover the actual ops_capture name via ALL_TOOLS if needed. '
            'Retrieve ops:// references using ops_result, without rerunning the source command. '
            'Direct-tool hooks cannot intercept exec text()/notify() output.')


def _session_start():
    guidance = GUIDANCE
    if runtime_status.current()['activeForThisProcess']:
        guidance = ('Codex Ops automatic runtime output compression is active. Keep complete tool values inside functions.exec '
                    'and use ordinary text()/notify(); large emitted text receives a retrievable ops:// reference. '
                    'Use ops_result with view="raw" for exact emitted text, following nextOffset; '
                    'do not rerun a source operation to recover display output. Script errors retain native diagnostics. '
                    'For a code question, call ops_workflow(operation="investigate",args={question:"...",anchors:["known_symbol"]}); '
                    'anchors are optional; use code identifiers when business terms are ambiguous. '
                    'For saved sources use operation="evidence",args={refs:[...],query:"terms"}; '
                    'for a log use diagnose,args={logPath:"relative.log"}; documents combines related inputs. '
                    'Pass an absolute root. Use returned content directly; retrieve only missing evidence. '
                    'Single known reads, writes and polling stay native. Set exec_command workdir explicitly. '
                    'ops_catalog(operation="workflows"|"task") provides direct recipes; SDK is optional.')
    return {'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': guidance}}


def _eligible_tool(name):
    return (name == 'Bash' or name.startswith('mcp__')) and not any(
        marker in name for marker in ('codex_ops', 'codex-ops'))


def _presentable(value):
    if has_media(value):
        return False
    if isinstance(value, dict):
        failures = (value.get('isError'), value.get('status') == 'error', value.get('exit_code') not in (None, 0))
        if any(failures):
            return False
    return len(encode(value).encode()) >= THRESHOLD


def _completion(event):
    if event['tool_name'] != 'Bash':
        return {}
    execution = shell_receipt.completed(event)
    if not execution:
        return None
    if execution['exit_code'] != 0 or execution['status'] != 'completed':
        return None
    return execution


def _capture(event, value, execution):
    store = Store()
    try:
        result = store.capture(value, scope=str(event.get('session_id', 'hook')))
        if result.get('kind') != 'reference':
            return None
        observation_metrics.reference(result, {'tool': event['tool_name'], 'session': event.get('session_id')})
        if execution:
            result['metadata'].update(execution)
        # Feedback remains tool data, never developer instructions. This preserves
        # code-mode Promise values, but cannot catch the script's text(result).
        return {'continue': False, 'stopReason': encode(result)}
    finally:
        store.close()


def _post_tool(event):
    if not _eligible_tool(event.get('tool_name', '')):
        return None
    value = event.get('tool_response')
    if not _presentable(value):
        return None
    # None means the native execution cannot authorize replacement; an empty
    # receipt is valid for MCP tools, which do not use Bash execution metadata.
    execution = _completion(event)
    if execution is None:
        return None
    return _capture(event, value, execution)


def process(event):
    if event.get('hook_event_name') == 'SessionStart':
        return _session_start()
    if event.get('hook_event_name') == 'PostToolUse':
        return _post_tool(event)
    return None


if __name__ == '__main__':
    try:
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
        output = process(json.load(sys.stdin))
        if output:
            print(encode(output))
    except Exception:
        # Any capture/serialization/storage failure leaves the host result intact.
        pass
