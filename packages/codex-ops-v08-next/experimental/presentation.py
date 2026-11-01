"""Experimental code-mode presentation transform. Never inspect delegate tool results."""
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from presentation_policy import Presenter


def compact(text):
    return Presenter().render(text)


def _notification(frame):
    request = frame.get('request', {})
    if request.get('type') != 'notification/send' or not isinstance(request.get('text'), str):
        return frame
    result = copy.deepcopy(frame)
    result['request']['text'] = compact(request['text'])
    return result


def _result_items(frame):
    """Locate completed content without treating errors or control messages as text."""
    envelope = frame.get('result', {})
    if envelope.get('status') != 'ok':
        return None
    outcome = envelope.get('value')
    if frame['type'] == 'operation/response':
        if not isinstance(outcome, dict) or outcome.get('type') != 'wait/completed':
            return None
        outcome = outcome.get('outcome', {}).get('LiveCell')
    return _completed_items(outcome)


def _completed_items(outcome):
    if not isinstance(outcome, dict):
        return None
    body = outcome.get('Result', outcome.get('Yielded'))
    if not isinstance(body, dict) or body.get('error_text') is not None:
        return None
    items = body.get('content_items')
    return items if isinstance(items, list) else None


def _compact_items(items):
    for item in items:
        if isinstance(item, dict) and item.get('type') == 'input_text' and isinstance(item.get('text'), str):
            item['text'] = compact(item['text'])


def _execution_output(frame):
    result = copy.deepcopy(frame)
    items = _result_items(result)
    if items is None:
        return frame
    _compact_items(items)
    return result


def output(frame):
    """Transform host -> client presentation only. Caller forwards client -> host untouched."""
    if not isinstance(frame, dict):
        return frame
    transform = {'delegate/request': _notification, 'execute/initialResponse': _execution_output,
                 'operation/response': _execution_output}.get(frame.get('type'))
    if transform is None:
        return frame
    return transform(frame)
