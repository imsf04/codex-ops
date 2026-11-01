"""Bounded explicit-file paths and content identities for native-shell mutations."""
import hashlib
import os
from pathlib import Path
import re
import stat

MAX_BYTES = 1024 * 1024
RESERVED = '.codex-ops-mutations'
CREDENTIAL = re.compile(r'(?i)(^|/)(id_(rsa|dsa|ecdsa|ed25519)(\.|$)|[^/]*credentials[^/]*\.(json|ya?ml|ini)$|service-account[^/]*\.json$|\.env(\.|$))')


class Conflict(ValueError):
    """A failed precondition; callers must inspect rather than retry blindly."""


def require(condition, message):
    if not condition:
        raise Conflict(message)


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else 'absent'


def _regular_components(path):
    for component in [*reversed(path.parents), path]:
        if not component.exists() and not component.is_symlink():
            continue
        info = component.lstat()
        linked = stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)
        require(not linked, 'Links and reparse points are not mutation paths')


def root_path(raw):
    path = Path(raw)
    require(path.is_absolute() and path.is_dir(), 'root must be an existing absolute directory')
    _regular_components(path)
    return path.resolve()


def target(root, raw, internal=False):
    require(isinstance(raw, str) and bool(raw), 'path must be a nonempty string')
    candidate = Path(os.path.abspath(root / raw))
    require(candidate.is_relative_to(root) and candidate != root, 'File path must remain inside root')
    parts = [part.lower() for part in candidate.relative_to(root).parts]
    require(internal or not {RESERVED, '.codex-ops-tasks'}.intersection(parts), 'Mutation journal paths are reserved')
    require('.dsh-ops' not in parts and not CREDENTIAL.search(candidate.as_posix()), 'Protected path')
    _regular_components(candidate)
    require(candidate.parent.is_dir(), 'Parent directory must already exist')
    return candidate


def read(path):
    if not path.exists():
        return None
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'Only regular, unlinked files are supported')
    require(info.st_size <= MAX_BYTES, 'Each file is limited to 1 MiB')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, 'File grew beyond the 1 MiB limit')
    return data


def states(root, names, internal=False):
    return {name: digest(read(target(root, name, internal))) for name in names}
