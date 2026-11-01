"""Transform known emitted text; preserve all source/tool values and error state bytes."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from presentation_policy import Presenter
from frame_dedup import FramePresenter
from output_budget import FrameBudget
from wire import fields, replace

SERVICE = '/codex.code_mode.v1.CodeModeHost/'
EXECUTIONS = {SERVICE + 'Execute': ('text', 2), SERVICE + 'Wait': ('wait', 1)}


def _content(data, transform):
    variants = fields(data)
    if len(variants) != 1 or variants[0].number != 1 or variants[0].wire != 2:
        return data
    return replace(data, 1, lambda body: replace(body, 1, transform))


def _known_error(state):
    if state.number != 5 or state.wire != 2:
        return False
    error = fields(state.value)
    return len(error) == 1 and error[0].number == 1 and error[0].wire == 2


def _eligible(state):
    return (state.number, state.wire, state.value) in ((3, 2, b''), (5, 2, b'')) or _known_error(state)


def _state(value):
    states = [item for item in value if item.number in (3, 4, 5)]
    if len(states) != 1:
        return None
    return states[0] if _eligible(states[0]) else None


def _has_cell(value):
    return any(item.number == 1 and item.wire == 2 for item in value)


def _error_measurement(state, presenter):
    diagnostic = fields(state.value)[0].value
    diagnostic.decode('utf-8')  # Unknown encodings retain the complete original frame.
    presenter.record('error', 'error_preserved', len(diagnostic), len(diagnostic))


def _execution(data, transform, presenter, record=True):
    value = fields(data)
    state = _state(value)
    if state is None:
        return data
    if not _has_cell(value):
        return data
    if state.number == 5 and state.value and record:
        _error_measurement(state, presenter)
    return replace(data, 2, lambda body: _content(body, transform))


def _text_transform(presenter, channel):
    def transform(data):
        return presenter.render(data.decode('utf-8'), channel).encode('utf-8')
    return transform


def _notification(data, transform, record=True):
    return replace(data, 3, lambda body: replace(body, 5, transform))


def _frame(data, presenter, channel, project_text, dedup=True):
    sizes = []
    def measure(raw):
        sizes.append(len(raw))
        return raw
    project_text(data, measure, False)
    renderer = FrameBudget(presenter, sizes)
    if dedup:
        renderer = FramePresenter(renderer)
    return project_text(data, _text_transform(renderer, channel))


def _execution_frame(field, presenter):
    def transform(body, text, record=True):
        return replace(body, field, lambda value: _execution(value, text, presenter, record))
    return transform


def project(method, data, presenter=None):
    presenter = presenter if presenter is not None else Presenter()
    try:
        if method == SERVICE + 'OpenSession':
            return _frame(data, presenter, 'notify', _notification, False)
        execution = EXECUTIONS.get(method)
        if execution is not None:
            return _frame(data, presenter, execution[0], _execution_frame(execution[1], presenter))
    except (ValueError, TypeError, UnicodeError):
        pass
    return data
