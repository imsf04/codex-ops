"""Return bounded complete table rows for literal cell matches, without rereading."""
import re

from reducers import encode

CELL = re.compile(r'^/items/(\d+)/cells/\d+$')
ROW_BYTES = 800


def _row(entry, result):
    match = CELL.fullmatch(entry['pointer'])
    if match is None:
        return entry
    index = int(match.group(1))
    row = result['items'][index]
    if len(encode(row).encode('utf-8')) > ROW_BYTES:
        return entry
    return {'pointer': f'/items/{index}', 'row': row}


def enrich(found, result):
    if not isinstance(result, dict) or not isinstance(result.get('columns'), list):
        return found
    rows = [_row(entry, result) for entry in found['items']]
    return {**found, 'items': rows, 'columns': result['columns']}
