"""Safe, read-only filesystem primitives (WI-SAFETY AC-04, AC-05).

Content reads `lstat` the path, require a regular file that is not dataless,
open it with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK`, and confirm through `fstat`
that the descriptor is the same regular file. Reading updates the file's
access time; that is the one unavoidable side effect (quantities.md).
"""

import errno
import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

SF_DATALESS = 0x40000000
CHUNK_SIZE = 1024 * 1024

StrPath = str | os.PathLike[str]

_KINDS = (
    (stat.S_ISREG, "file"),
    (stat.S_ISDIR, "directory"),
    (stat.S_ISLNK, "symlink"),
    (stat.S_ISFIFO, "fifo"),
    (stat.S_ISCHR, "character_device"),
    (stat.S_ISBLK, "block_device"),
    (stat.S_ISSOCK, "socket"),
)

_COVERAGE_REASONS = {
    errno.EACCES: "permission_denied",
    errno.EPERM: "privacy_denied",
    errno.ENOENT: "vanished",
}


class FsReadError(Exception):
    """Base class for refused reads; `reason` is an incomplete_coverage reason."""

    reason = "read_error"

    def __init__(self, path: StrPath, message: str) -> None:
        super().__init__(message)
        self.path = os.fspath(path)


class NotRegularFileError(FsReadError):
    """The entry is a FIFO, device, socket, symlink, or directory."""

    reason = "not_regular_file"

    def __init__(self, path: StrPath, kind: str) -> None:
        super().__init__(path, f"not a regular file ({kind}): {os.fspath(path)}")
        self.kind = kind


class DatalessFileError(FsReadError):
    """The file is a dataless placeholder; opening it would trigger a download."""

    reason = "dataless"

    def __init__(self, path: StrPath) -> None:
        super().__init__(path, f"dataless file not opened: {os.fspath(path)}")


class IdentityChangedError(FsReadError):
    """The opened descriptor is not the entry that was checked with lstat."""

    reason = "changed_during_scan"

    def __init__(self, path: StrPath) -> None:
        super().__init__(
            path, f"file changed between lstat and open: {os.fspath(path)}"
        )


def lstat(path: StrPath) -> os.stat_result:
    """Return stat information for path without following a symlink."""
    return os.lstat(path)


def is_dataless(info: Any) -> bool:
    """Report whether SF_DATALESS is set in the entry's st_flags."""
    return bool(getattr(info, "st_flags", 0) & SF_DATALESS)


def entry_kind(mode: int) -> str:
    """Name the file type encoded in st_mode."""
    for predicate, name in _KINDS:
        if predicate(mode):
            return name
    return "unknown"


def coverage_reason(code: int | None) -> str:
    """Map an errno value to an incomplete_coverage reason."""
    return (
        _COVERAGE_REASONS.get(code, "read_error") if code is not None else "read_error"
    )


def _require_readable(path: StrPath, info: Any) -> None:
    kind = entry_kind(info.st_mode)
    if kind != "file":
        raise NotRegularFileError(path, kind)
    if is_dataless(info):
        raise DatalessFileError(path)


@contextmanager
def open_regular_file(path: StrPath) -> Iterator[int]:
    """Yield a read-only descriptor for a verified regular, local file."""
    before = lstat(path)
    _require_readable(path, before)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        after = os.fstat(fd)
        same = (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
        if not same or not stat.S_ISREG(after.st_mode):
            raise IdentityChangedError(path)
        if is_dataless(after):
            raise DatalessFileError(path)
        yield fd
    finally:
        os.close(fd)


@dataclass(frozen=True)
class FileHash:
    """Content digest of one file and the bytes read to compute it."""

    digest: str
    bytes_read: int


def hash_file(path: StrPath, algorithm: str = "sha256") -> FileHash:
    """Hash a regular file through open_regular_file, in fixed-size chunks."""
    digest = hashlib.new(algorithm)
    total = 0
    with open_regular_file(path) as fd:
        while chunk := os.read(fd, CHUNK_SIZE):
            digest.update(chunk)
            total += len(chunk)
    return FileHash(digest.hexdigest(), total)


@dataclass(frozen=True)
class WalkEntry:
    """One entry seen by the walker, with its lstat result."""

    path: str
    stat: Any

    @property
    def kind(self) -> str:
        return entry_kind(self.stat.st_mode)

    @property
    def is_dataless(self) -> bool:
        return is_dataless(self.stat)


@dataclass(frozen=True)
class SkippedMount:
    """A directory on another device; it is neither counted nor entered."""

    path: str


@dataclass(frozen=True)
class WalkError:
    """An entry the walker could not observe."""

    path: str
    operation: str
    reason: str
    errno_name: str | None


WalkItem = WalkEntry | SkippedMount | WalkError


def _entry_lstat(entry: os.DirEntry[str]) -> Any:
    return entry.stat(follow_symlinks=False)


def _walk_error(path: str, operation: str, error: OSError) -> WalkError:
    name = errno.errorcode.get(error.errno) if error.errno is not None else None
    return WalkError(path, operation, coverage_reason(error.errno), name)


def _sorted_entries(path: str) -> list[os.DirEntry[str]]:
    with os.scandir(path) as iterator:
        return sorted(iterator, key=lambda entry: os.fsencode(entry.name))


DirEntries = Iterator[os.DirEntry[str]]


def _open_dir(path: str, info: Any) -> tuple[list[WalkItem], DirEntries | None]:
    """List a directory unless it is dataless or unreadable."""
    if is_dataless(info):
        return [WalkError(path, "scandir", "dataless", None)], None
    try:
        return [], iter(_sorted_entries(path))
    except OSError as error:
        return [_walk_error(path, "scandir", error)], None


def _step(
    entry: os.DirEntry[str], root_dev: int
) -> tuple[list[WalkItem], DirEntries | None]:
    """Classify one entry and, for a same-device directory, list its children."""
    try:
        info = _entry_lstat(entry)
    except OSError as error:
        return [_walk_error(entry.path, "lstat", error)], None
    is_dir = stat.S_ISDIR(info.st_mode)
    if is_dir and info.st_dev != root_dev:
        return [SkippedMount(entry.path)], None
    item = WalkEntry(entry.path, info)
    if not is_dir:
        return [item], None
    extra, children = _open_dir(entry.path, info)
    return [item, *extra], children


def walk(root: StrPath) -> Iterator[WalkItem]:
    """Walk root depth-first in byte order of names, never following symlinks.

    The walk is iterative, with an explicit stack of sorted listings. A
    directory on a different st_dev than root is reported as SkippedMount and
    not entered. A dataless directory is yielded, then reported as a
    WalkError with reason `dataless`, and never listed. The root itself is not
    yielded.
    """
    root_path = os.fspath(root)
    info = lstat(root_path)
    if not stat.S_ISDIR(info.st_mode):
        raise NotADirectoryError(
            errno.ENOTDIR, "scan root is not a directory", root_path
        )
    items, entries = _open_dir(root_path, info)
    yield from items
    stack = [entries] if entries is not None else []
    while stack:
        entry = next(stack[-1], None)
        if entry is None:
            stack.pop()
            continue
        items, children = _step(entry, info.st_dev)
        yield from items
        if children is not None:
            stack.append(children)
