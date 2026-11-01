"""Copy a SQLite database while holding its POSIX database and WAL locks."""
import fcntl
import os
from pathlib import Path
import shutil
import sys


def copy(path, destination, maximum):
    wal = path.with_name(path.name + '-wal')
    shm = path.with_name(path.name + '-shm')
    # SQLite's pending, reserved and shared bytes, and WAL write/checkpoint/recovery locks.
    with path.open('rb') as main:
        fcntl.lockf(main, fcntl.LOCK_SH | fcntl.LOCK_NB, 512, 0x40000000)
        initial_shm = shm.exists()
        lock = shm.open('rb') if initial_shm else None
        try:
            if lock:
                fcntl.lockf(lock, fcntl.LOCK_SH | fcntl.LOCK_NB, 3, 120)
            used = _copy(main, destination, maximum)
            if wal.exists():
                with wal.open('rb') as stream:
                    _copy(stream, destination.with_name(destination.name + '-wal'), maximum - used)
            # A new WAL index means a connection opened while the files were copied.
            if not initial_shm and shm.exists():
                raise OSError('SQLite WAL index appeared during the read-only snapshot')
        finally:
            if lock:
                lock.close()


def _copy(source, destination, remaining):
    size = os.fstat(source.fileno()).st_size
    if size > remaining:
        raise ValueError('Reference database snapshot exceeds its 256 MiB bound')
    with destination.open('xb') as target:
        shutil.copyfileobj(source, target, 1024 * 1024)
    return size


if __name__ == '__main__':
    try:
        copy(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
