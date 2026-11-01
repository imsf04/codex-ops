"""Correlate a Bash hook with a completed native execution, or leave it untouched."""
import json
from pathlib import Path

MAX_TAIL = 2 * 1024 * 1024


def _records(path):
    with Path(path).open('rb') as stream:
        stream.seek(0, 2)
        start = max(0, stream.tell() - MAX_TAIL)
        stream.seek(start)
        if start:
            stream.readline()  # Ignore a partial JSON line at the seam.
        lines = stream.read(MAX_TAIL).splitlines()
    for line in reversed(lines):
        try:
            yield json.loads(line)
        except (ValueError, UnicodeError):
            continue


def _matching_item(record, event):
    value = record.get('payload', {})
    item = value.get('item', {})
    actual = (record.get('type'), value.get('type'), item.get('type'), item.get('id'),
              value.get('thread_id'), value.get('turn_id'))
    expected = ('event_msg', 'item_completed', 'CommandExecution', event.get('tool_use_id'),
                event.get('session_id'), event.get('turn_id'))
    return item if actual == expected else None


def _command_matches(item, event):
    command = item.get('command')
    return isinstance(command, list) and bool(command) and command[-1] == event.get('tool_input', {}).get('command')


def _output_matches(item, event):
    aggregate = item.get('aggregated_output')
    return isinstance(aggregate, str) and bool(event['tool_response']) and aggregate.endswith(event['tool_response'])


def _receipt(item, output):
    aggregate = item['aggregated_output']
    return {'exit_code': item['exit_code'], 'status': item['status'],
            'process_id': item.get('process_id'), 'executionComplete': True,
            'observationScope': 'execution-output' if aggregate == output else 'final-chunk',
            'executionOutputCharacters': len(aggregate), 'capturedOutputCharacters': len(output),
            'statusEvidence': 'matched native CommandExecution event'}


def _validated_receipt(item, event):
    if not _command_matches(item, event):
        return None
    if not _output_matches(item, event):
        return None
    if type(item.get('exit_code')) is not int:
        return None
    if item.get('status') not in ('completed', 'failed'):
        return None
    return _receipt(item, event['tool_response'])


def _find_receipt(event):
    path = event.get('transcript_path')
    if not isinstance(path, str) or not isinstance(event.get('tool_response'), str):
        return None
    for record in _records(path):
        item = _matching_item(record, event)
        if item is not None:
            # A newer matching but invalid record must not authorize an older one.
            return _validated_receipt(item, event)
    return None


def completed(event):
    # Bash's tool_response contains text only, not the process status. Never infer
    # success from output or command text; only a correlated receipt is evidence.
    try:
        return _find_receipt(event)
    except (OSError, ValueError, TypeError, AttributeError):
        return None
