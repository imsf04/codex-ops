"""Copy a quiescent Windows SQLite database under a read-only sharing lock."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import tempfile

MAX_BYTES = 256 * 1024 * 1024


def _locked_reader(path):
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    open_file = kernel.CreateFileW
    open_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_file.restype = wintypes.HANDLE
    handle = open_file(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY), 'rb')


def _copy(stream, target, remaining):
    size = os.fstat(stream.fileno()).st_size
    if size > remaining:
        raise ValueError('Reference database snapshot exceeds its 256 MiB bound')
    with target.open('xb') as output:
        shutil.copyfileobj(stream, output, 1024 * 1024)
    return size


@contextmanager
def database(path):
    if os.name != 'nt':
        raise OSError('Read-only task snapshots are not yet available on this platform')
    # FILE_SHARE_READ permits other readers but rejects existing/new DB writers.
    # SQLite WAL writers also hold a write-capable main database handle.
    with _locked_reader(path) as source, tempfile.TemporaryDirectory(prefix='codex-ops-ref-') as temporary:
        destination = Path(temporary) / 'observation.sqlite3'
        used = _copy(source, destination, MAX_BYTES)
        wal = path.with_name(path.name + '-wal')
        if wal.exists():
            with _locked_reader(wal) as stream:
                _copy(stream, destination.with_name(destination.name + '-wal'), MAX_BYTES - used)
        # The source lock covers both copies; recovery/index files belong only to this temporary directory.
        yield destination
