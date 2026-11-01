"""Read this app-server's bridge status without inspecting saved observations."""
import json
import os
from pathlib import Path
import subprocess
import time
import ctypes
from ctypes import wintypes


_INACTIVE = {'activeForThisProcess': False, 'reason': 'Native host bridge is not attached to this app-server'}


def _process_parents():
    """Collect parent IDs without retaining process handles."""
    if os.name != 'nt':
        try:
            output = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid='], capture_output=True,
                                    text=True, check=True, timeout=2).stdout
            return {int(pid): int(parent) for pid, parent in
                    (line.split() for line in output.splitlines())}
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
    class Entry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                    ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG), ('flags', wintypes.DWORD),
                    ('exe', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return None
    parents = {}
    try:
        entry = Entry(size=ctypes.sizeof(Entry))
        available = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            parents[entry.pid] = entry.parent
            available = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return parents


def ancestors():
    # MCP processes may receive a filtered environment. Correlate their actual
    # native ancestry instead of claiming any globally running relay is theirs.
    parents = _process_parents()
    if parents is None:
        return []
    result, current = [], os.getpid()
    while current and current not in result and len(result) < 32:
        result.append(current)
        current = parents.get(current)
    return result


def _declared_status(root, shim):
    value = json.loads((root / f'{shim}.json').read_text(encoding='utf-8'))
    return value if value.get('shimPid') == int(shim) else None


def _fresh(value):
    updated = value.get('updatedAt')
    return (value.get('state') == 'ready' and isinstance(updated, (int, float))
            and time.time() - updated <= 5)


def _lineage_candidates(root, lineage):
    for path in root.glob('*.json'):
        try:
            candidate = json.loads(path.read_text(encoding='utf-8'))
            if candidate.get('shimPid') in lineage and _fresh(candidate):
                yield candidate
        except (OSError, ValueError):
            continue


def _selected_status(root):
    shim = os.environ.get('CODEX_OPS_BRIDGE_SHIM_PID', '')
    if shim.isdecimal() and os.environ.get('CODEX_OPS_AUTO_OUTPUT') == '1':
        return _declared_status(root, shim)
    lineage = ancestors()
    return min(_lineage_candidates(root, lineage),
               key=lambda item: (lineage.index(item['shimPid']), -item.get('updatedAt', 0)), default=None)


def _describe_status(value):
    if not _fresh(value):
        return {**_INACTIVE, 'reason': 'Bridge status is stale or unavailable'}
    return {'activeForThisProcess': bool(value.get('compressionEnabled')), 'managerPid': value['pid'],
            'runtimeVersion': value.get('runtimeVersion'),
            'nativeHostPid': value['nativeHostPid'], 'counters': value['counters'],
            'reason': 'Automatic output compression active' if value.get('compressionEnabled') else 'Unvalidated host version; forwarding unchanged'}


def current():
    root = Path(os.environ.get('CODEX_OPS_BRIDGE_STATUS', str(Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'CodexOps/bridge')))
    try:
        value = _selected_status(root)
        if value is not None:
            return _describe_status(value)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return dict(_INACTIVE)
