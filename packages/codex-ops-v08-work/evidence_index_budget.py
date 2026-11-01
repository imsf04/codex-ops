"""Whole-packet UTF-8 budgets with explicit omission accounting."""
import copy
import json


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def _drop(value, field):
    rows = value.get(field, [])
    if not rows:
        return False
    rows.pop()
    omitted = value.setdefault('omitted', {})
    omitted[field] = omitted.get(field, 0) + 1
    return True


def _reduce(value):
    for field in ('items', 'sources', 'pending'):
        if _drop(value, field):
            return True
    if value.get('title'):
        value['title'] = ''
        value.setdefault('omitted', {})['title'] = True
        return True
    return False


def _partial(value):
    value['status'] = 'partial'
    value['selectionComplete'] = False
    value.setdefault('coverage', {})['selectionComplete'] = False


def bounded(value, maximum):
    result = copy.deepcopy(value)
    while size(result) > maximum:
        _partial(result)
        if not _reduce(result):
            raise ValueError('Evidence metadata exceeds output budget; narrow the request')
    return result
