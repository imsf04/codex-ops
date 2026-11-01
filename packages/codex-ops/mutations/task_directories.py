"""Directory effects: Windows rename exclusion; POSIX opened-directory authority."""
from contextlib import contextmanager, ExitStack
import ctypes
import os
from ctypes import wintypes
from .paths import target, _regular_components


@contextmanager
def _hold(path):
    if os.name == 'posix':
        # Open each component relative to the preceding directory. O_NOFOLLOW on
        # a single absolute open would still follow symlinks in its ancestors.
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = os.open(path.anchor, flags)
        try:
            for part in path.parts[1:]:
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            yield descriptor
        finally:
            os.close(descriptor)
        return
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
    if os.name == 'posix':
        with _hold(path.parent) as parent:
            # A rename preserves authority over the opened directory identity.
            # mkdirat/rmdirat do not follow a symlink in the final component.
            operation = os.mkdir if create else os.rmdir
            operation(path.name, dir_fd=parent)
        return
    with ExitStack() as stack:
        for parent in reversed(path.parents):
            stack.enter_context(_hold(parent))
        _regular_components(path)
        path.mkdir() if create else path.rmdir()
