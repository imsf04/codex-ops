"""Deterministic previews; saved observations remain unmodified."""
import json
import re
from structured import analyze
from record_preview import preview as record_preview
from semantic_preview import diagnostic, failure, source_text
from evidence_preview import preview as evidence_preview, records as record_evidence



def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def clip(text, budget):
    return text.encode('utf-8')[:max(0, budget)].decode('utf-8', errors='ignore')


def payload(value):
    return analyze(value)['value']


def metadata(value):
    result = analyze(value)['metadata']
    # Large errors are preserved in storage; the preview labels clipping explicitly.
    return {k: v if len(encode(v).encode()) < 900 else {'preview': clip(encode(v), 800), 'clipped': True}
            for k, v in result.items()}


def small(value, depth=0):
    if isinstance(value, str):
        return _small_text(value)
    if isinstance(value, list):
        return _small_sequence(value, depth)
    if isinstance(value, dict):
        return _small_mapping(value, depth)
    return value


def _small_text(value):
    return value if len(value.encode()) <= 180 else {'textPreview': clip(value, 160), 'bytes': len(value.encode())}


def _small_sequence(value, depth):
    if depth >= 3:
        return {'itemCount': len(value)}
    return {'itemCount': len(value), 'sample': [small(v, depth + 1) for v in value[:2]]}


def _small_mapping(value, depth):
    if depth >= 3:
        return {'keys': list(value)[:15], 'keyCount': len(value)}
    preferred = ['id', 'name', 'path', 'title', 'status', 'error', 'message', 'url']
    keys = list(dict.fromkeys([k for k in preferred if k in value] + list(value)))
    return {k: small(value[k], depth + 1) for k in keys[:12]}


def _fold_lines(lines):
    folded = []
    for n, line in enumerate(lines, 1):
        if folded and line == folded[-1][1]:
            folded[-1][2] += 1
        else:
            folded.append([n, line, 1])
    return folded


def _is_diff(text, lines):
    return text.startswith('diff --git') or any(line.startswith('@@ ') for line in lines)


def _notable_line(line, diff):
    return diagnostic(line) or (diff and line.startswith(('diff ', '-', '+', '@@ ')))


def _selected_lines(folded, diff, source=False):
    edges = set(range(min(6, len(folded)))) | set(range(max(0, len(folded) - 6), len(folded)))
    notable = set() if source else {i for i, (_, line, _) in enumerate(folded) if _notable_line(line, diff)}
    # Reserve space for the tail even when a build reports thousands of diagnostics.
    return sorted(edges | set(sorted(notable - edges)[:12]))


def _render_line(row, per_line):
    number, line, count = row
    suffix = f' [repeated {count} times]' if count > 1 else ''
    truncated = ' [line clipped]' if len(line.encode()) > per_line else ''
    return f'{number}: {clip(line, per_line)}{truncated}{suffix}'


def _text_kind(diff, lines, source=False):
    if diff:
        return 'diff'
    return 'diagnostic-log' if not source and any(diagnostic(line) for line in lines) else 'text'


def text_preview(text, budget):
    lines = text.splitlines()
    folded = _fold_lines(lines)
    diff = _is_diff(text, lines)
    source = source_text(lines) and not diff
    chosen = _selected_lines(folded, diff, source)
    per_line = max(40, budget // max(1, len(chosen)) - 35)
    rendered = [_render_line(folded[index], per_line) for index in chosen]
    result = {'kind': _text_kind(diff, lines, source), 'lineCount': len(lines), 'foldedLineCount': len(folded),
              'selectedLines': len(chosen), 'text': clip('\n'.join(rendered), budget)}
    diagnostics = [] if source else _failure_lines(lines, budget)
    if diagnostics:
        result['diagnostics'] = diagnostics
    return result


def _failure_lines(lines, budget):
    selected = []
    width = max(16, min(200, budget // 8))
    for line in lines:
        if failure(line):
            selected.append(clip(line, width))
            if len(selected) == 3:
                break
    return selected


def preview(value, budget=3500):
    analysis = analyze(value)
    data = analysis['value']
    if isinstance(data, dict) and isinstance(data.get('output'), str):
        result = _output_preview(data, analysis['metadata'], budget)
    elif isinstance(data, str):
        result = text_preview(data, max(40, budget - 150))
    else:
        return _json_preview(data, budget)
    return _fit_text(result, budget)


def _execution_state(value):
    keys = ('exit_code', 'session_id', 'status', 'isError', 'truncated', 'complete')
    return {key: value[key] for key in keys if key in value}


def _output_preview(data, state, budget):
    evidence = evidence_preview({'kind': 'shell', 'value': data, 'metadata': state}, max(160, budget - 400))
    if evidence is not None:
        return {**evidence, **_execution_state(state)}
    output = analyze(data['output'])['value']
    reserved = max(40, budget - 400)
    if isinstance(output, (dict, list)):
        result = _json_preview(output, reserved)
    else:
        result = text_preview(data['output'], reserved)
    result.update(_execution_state(state))
    return result


def _fit_text(result, budget):
    if len(encode(result).encode()) <= budget:
        return result
    result['clipped'] = True
    while len(encode(result).encode()) > budget:
        text = result.get('text', '')
        if len(text) < 8:
            return {'kind': result['kind'], 'clipped': True}
        width = len(text) // 4
        result['text'] = text[:width] + ' … ' + text[-width:]
    return result


def _json_preview(data, budget):
    specialized = record_preview(data, budget)
    if specialized is None:
        specialized = record_evidence(data, budget)
    if specialized is not None:
        return specialized
    for depth in (0, 2, 3):
        result = {'kind': 'json', 'sample': small(data, depth), 'clipped': depth > 0}
        if len(encode(result).encode()) <= budget:
            return result
    return {'kind': 'json', 'valueType': type(data).__name__, 'clipped': True}


def has_media(value):
    return isinstance(value, dict) and isinstance(value.get('content'), list) and any(
        b.get('type') not in ('text',) for b in value['content'])
