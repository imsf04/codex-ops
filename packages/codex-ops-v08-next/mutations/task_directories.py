"""Native directory effects with Windows parent rename/reparse exclusion."""
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
from .paths import target, _regular_components


@contextmanager
def _hold(path):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    # GENERIC_READ participates in sharing checks; attribute-only handles do not.
    handle = create(str(path), 0x80000000, 3, None, 3, 0x02000000 | 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    try:
        _regular_components(path)
        yield
    finally:
        close(handle)


def execute(root, name, create):
    path = target(root, name)
    with ExitStack() as stack:
        for parent in reversed(path.parents):
            stack.enter_context(_hold(parent))
        _regular_components(path)
        path.mkdir() if create else path.rmdir()
