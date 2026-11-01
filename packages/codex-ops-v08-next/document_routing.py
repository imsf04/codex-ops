"""Select existing permissioned readers before opening a document as text."""
from pathlib import PurePath

from workflow_validation import require

FORMATS = {'.docx': ('read_docx', 'paragraph', 1000), '.pdf': ('read_pdf', 'page', 32),
           '.csv': ('read_table', 'row', 1000), '.tsv': ('read_table', 'row', 1000)}


def _format(entry):
    require(isinstance(entry, dict) and isinstance(entry.get('path'), str), 'Each read file requires a path')
    return FORMATS.get(PurePath(entry['path']).suffix.lower())


def _typed(entry, selected, index):
    operation, unit, maximum = selected
    require(set(entry) <= {'path', 'offset', 'limit'}, 'Document read accepts path, offset and limit')
    args = dict(entry)
    requested = args.get('limit', 200)
    require(type(requested) is int and 1 <= requested <= 10000, 'Document limit must be 1..10000')
    args['limit'] = min(requested, maximum)
    return {'operation': operation, 'args': args}, {'requestIndex': index, 'from': 'read',
            'sourcePath': entry['path'], 'offsetUnit': unit, 'requestedLimit': requested,
            'appliedLimit': args['limit']}


def _read(request, index):
    args = request['args']
    require(set(args) == {'files'}, 'read args must contain only files')
    entries = args['files']
    require(isinstance(entries, list) and 1 <= len(entries) <= 32, 'read requires 1..32 files')
    selected = [_format(entry) for entry in entries]
    if not any(selected):
        return [(request, None)]
    return [_typed(entry, fmt, index) if fmt else
            ({'operation': 'read', 'args': {'files': [entry]}}, {'requestIndex': index,
             'from': 'read', 'sourcePath': entry['path'], 'offsetUnit': 'line'})
            for entry, fmt in zip(entries, selected)]


def normalize(requests):
    routed = []
    for index, request in enumerate(requests):
        routed.extend(_read(request, index) if request['operation'] == 'read' else [(request, None)])
    require(len(routed) <= 4, 'Format-aware documents supports at most 4 independent reads; split these sources into another request')
    return [request for request, _ in routed], [route for _, route in routed]
