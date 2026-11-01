"""Read-only, bounded mutation journal summaries for one explicitly selected root."""
import itertools
import json
import os
from pathlib import Path
import re
import stat

from mutations.paths import root_path

MAX_TASKS = 64
MAX_SCAN = 512
MAX_BYTES = 16 * 1024 * 1024
MAX_FILE = 10 * 1024 * 1024
PHASES = frozenset(('ready', 'applying', 'completed', 'needs-inspection', 'rolling-back', 'rolled-back'))


def _regular(path, directory=False):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Journal links are not followed')
    valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid:
        raise ValueError('Journal entry has an unexpected file type')
    return info


class _ByteBudget:
    def __init__(self, remaining):
        self.remaining = remaining

    def read(self, path):
        info = _regular(path)
        limit = min(MAX_FILE, self.remaining)
        if info.st_size > limit:
            raise ValueError('Journal byte budget reached')
        with path.open('rb') as stream:
            # Reserve the request before IO; a failed read may have consumed bytes
            # without returning them. Successful reads refund the unused portion.
            self.remaining -= limit
            raw = stream.read(limit)
            self.remaining += limit - len(raw)
            if len(raw) > limit or os.fstat(stream.fileno()).st_size > limit:
                raise ValueError('Journal grew beyond byte budget')
        return raw, info.st_mtime


def _summary(path, identity, budget):
    raw, updated = budget.read(path)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Journal must be an object')
    if value.get('id') != identity or value.get('phase') not in PHASES:
        raise ValueError('Journal identity or phase is invalid')
    return {'journalId': identity, 'phase': value['phase'], 'operationCount': len(value['plan']['items']),
            'hasError': value.get('error') is not None, 'updatedAt': updated}


def _entries(directory):
    entries = list(itertools.islice(directory.iterdir(), MAX_SCAN + 1))
    limited = len(entries) > MAX_SCAN
    selected = [path for path in entries[:MAX_SCAN] if re.fullmatch('[0-9a-f]{32}', path.name)]
    return selected, limited


def _scan(directory):
    entries, truncated = _entries(directory)
    rows, budget, rejected = [], _ByteBudget(MAX_BYTES), 0
    for entry in entries:
        if len(rows) >= MAX_TASKS or budget.remaining <= 0:
            truncated = True
            break
        try:
            _regular(entry, True)
            row = _summary(entry / 'journal.json', entry.name, budget)
            rows.append(row)
        except (OSError, ValueError, KeyError, TypeError):
            rejected += 1
    return rows, truncated, rejected


def snapshot(root=None):
    result = {'enabled': root is not None, 'items': [], 'complete': True, 'rejectedEntries': 0,
              'measurement': 'Saved journal phases only; current file postconditions are not revalidated'}
    if root is None:
        return result
    try:
        directory = _directory(root)
        if directory is None:
            return result
        rows, truncated, rejected = _scan(directory)
        result.update(items=sorted(rows, key=lambda row: row['updatedAt'], reverse=True),
                      complete=not truncated and not rejected, rejectedEntries=rejected)
    except (OSError, ValueError):
        result.update(complete=False, rejectedEntries=1)
    return result


def _directory(root):
    directory = root_path(root) / '.codex-ops-mutations'
    try:
        _regular(directory, True)
    except FileNotFoundError:
        return None
    return directory
