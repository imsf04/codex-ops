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
        guidance = ('Codex Ops automatic output compression is active; full functions.exec program values stay intact. '
                    'Basic calls are self-contained: in one functions.exec use '
                    'text(await tools.mcp__codex_ops__ops_workflow({root:"absolute directory",question:"code question"})). '
                    'If the tool prefix differs, resolve its name from ALL_TOOLS and invoke it in that same exec. '
                    'For related documents pass operation:"documents",args:{requests:[{operation:"read",args:{files:[{path:"policy.docx"}]}}]}; '
                    'text, DOCX, PDF and tables route automatically. For logs use operation:"diagnose",args:{logPath:"build.log"}; '
                    'for acquired refs use operation:"evidence",args:{refs:[...],query:"terms"}. '
                    'Use delivered evidence to finish when it answers the task. workingSet.state="saved" means available for later; '
                    'operation:"working_set",args:{action:"resume"} is for later recovery or changed sources. '
                    'A stale source remains stale; separate current-read evidence has its own revision and coverage. '
                    'For output use ordinary text()/notify(); ops_result(view="raw") and nextOffset recover exact emitted text without rerunning sources. '
                    'Single known reads, writes and polling stay native; set exec_command workdir. '
                    'Native exit/session state stays authoritative. The compact-output skill and ops_catalog("workflows") cover advanced contracts; SDK is optional.')
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
