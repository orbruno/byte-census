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
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Any, Self

SF_DATALESS = 0x40000000
CHUNK_SIZE = 1024 * 1024
# Directory descriptors the walker keeps open besides the root; deeper
# ancestors are closed and reopened by an O_NOFOLLOW openat chain.
FD_CAP = 16
CHANGED = "changed_during_scan"
# errno values from O_NOFOLLOW (and O_DIRECTORY) when a directory was
# replaced by a symlink or another kind of entry.
_SWAP_ERRNOS = frozenset({errno.ELOOP, errno.ENOTDIR})

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
    """Return stat information for path without following a symlink.

    A path produced by the walker for a listed entry is resolved relative to
    its open parent descriptor, never through the path string.
    """
    if isinstance(path, _BoundPath):
        return os.stat(path.name, dir_fd=path.dir_fd, follow_symlinks=False)
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


class FileTooLargeError(FsReadError):
    """The file exceeds the size limit for a small configuration read."""

    reason = "too_large"

    def __init__(self, path: StrPath, limit: int) -> None:
        super().__init__(path, f"file exceeds {limit} bytes: {os.fspath(path)}")
        self.limit = limit


def read_small_file(path: StrPath, limit: int) -> bytes:
    """Read a whole regular file of at most `limit` bytes through the safe opener."""
    chunks: list[bytes] = []
    total = 0
    with open_regular_file(path) as fd:
        while chunk := os.read(fd, CHUNK_SIZE):
            total += len(chunk)
            if total > limit:
                raise FileTooLargeError(path, limit)
            chunks.append(chunk)
    return b"".join(chunks)


@dataclass(frozen=True)
class FileHash:
    """Content digest of one file and the bytes read to compute it."""

    digest: str
    bytes_read: int


def _digest(fd: int, algorithm: str) -> FileHash:
    digest = hashlib.new(algorithm)
    total = 0
    while chunk := os.read(fd, CHUNK_SIZE):
        digest.update(chunk)
        total += len(chunk)
    return FileHash(digest.hexdigest(), total)


def hash_file(path: StrPath, algorithm: str = "sha256") -> FileHash:
    """Hash a regular file through open_regular_file, in fixed-size chunks."""
    with open_regular_file(path) as fd:
        return _digest(fd, algorithm)


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


class _BoundPath(str):
    """A path string that also names an entry relative to an open directory.

    Seams such as `lstat` and `_sorted_entries` keep receiving the familiar
    path string, so patched test doubles still match on it, while the real
    implementations resolve `name` relative to `dir_fd` and never follow the
    path string itself.
    """

    dir_fd: int
    name: str

    def __new__(cls, path: str, dir_fd: int, name: str) -> Self:
        bound = super().__new__(cls, path)
        bound.dir_fd = dir_fd
        bound.name = name
        return bound


class _FdHandle(int):
    """An open directory descriptor whose `os.fspath` is its path.

    `os.scandir` treats it as a descriptor; error messages and test doubles
    that call `os.fspath` see the directory's path.
    """

    path: str

    def __new__(cls, fd: int, path: str) -> Self:
        handle = super().__new__(cls, fd)
        handle.path = path
        return handle

    def __fspath__(self) -> str:
        return self.path


@dataclass(frozen=True)
class _Entry:
    """One listed name, its display path, and the descriptor it is relative to."""

    name: str
    path: str
    dir_fd: int


@dataclass(frozen=True)
class _Frame:
    """One open (or temporarily closed) directory on the walk stack."""

    path: str
    parts: tuple[str, ...]
    info: Any
    names: Iterator[str]
    fd: int | None


def _entry_lstat(entry: _Entry) -> Any:
    return os.stat(entry.name, dir_fd=entry.dir_fd, follow_symlinks=False)


def _identity(info: Any) -> tuple[int, int]:
    return (info.st_dev, info.st_ino)


def _walk_error(path: str, operation: str, error: OSError) -> WalkError:
    name = errno.errorcode.get(error.errno) if error.errno is not None else None
    return WalkError(str(path), operation, coverage_reason(error.errno), name)


def _sorted_entries(path: _BoundPath) -> list[_Entry]:
    with os.scandir(_FdHandle(path.dir_fd, str(path))) as iterator:
        names = sorted((entry.name for entry in iterator), key=os.fsencode)
    return [_Entry(name, os.path.join(path, name), path.dir_fd) for name in names]


def _dir_open_error(path: str, error: OSError, expected: Any) -> WalkError:
    """Map a directory open failure; a directory that turned into anything else
    (a symlink gives ELOOP or ENOTDIR under O_NOFOLLOW) has changed."""
    if stat.S_ISDIR(expected.st_mode) and error.errno in _SWAP_ERRNOS:
        name = errno.errorcode.get(error.errno) if error.errno is not None else None
        return WalkError(str(path), "scandir", CHANGED, name)
    return _walk_error(path, "scandir", error)


def _open_directory(
    path: str, parent_fd: int | None, name: str, expected: Any
) -> tuple[int | None, WalkError | None]:
    """Open a directory without following symlinks and confirm its identity."""
    target = name if parent_fd is not None else path
    try:
        fd = os.open(
            target,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except OSError as error:
        return None, _dir_open_error(path, error, expected)
    try:
        same = _identity(os.fstat(fd)) == _identity(expected)
    except OSError as error:
        os.close(fd)
        return None, _walk_error(path, "scandir", error)
    if not same:
        os.close(fd)
        return None, WalkError(str(path), "scandir", CHANGED, None)
    return fd, None


def _list_names(path: str, fd: int) -> tuple[list[str], WalkError | None]:
    try:
        entries = _sorted_entries(_BoundPath(path, fd, "."))
    except OSError as error:
        return [], _walk_error(path, "scandir", error)
    return [entry.name for entry in entries], None


Prune = Callable[[WalkEntry], bool] | None


def _step(
    frame: _Frame, name: str, root_dev: int, prune: Prune
) -> tuple[list[WalkItem], _Frame | None]:
    """Classify one child of `frame`; for a local directory, open and list it."""
    path = os.path.join(frame.path, name)
    try:
        info = _entry_lstat(_Entry(name, path, frame.fd))
    except OSError as error:
        return [_walk_error(path, "lstat", error)], None
    if info.st_dev != root_dev:
        return [SkippedMount(path)], None
    item = WalkEntry(path, info)
    if not stat.S_ISDIR(info.st_mode):
        return [item], None
    if prune is not None and prune(item):
        return [item], None
    if is_dataless(info):
        return [item, WalkError(path, "scandir", "dataless", None)], None
    fd, error = _open_directory(path, frame.fd, name, info)
    if fd is None:
        return [item, *([error] if error else [])], None
    names, error = _list_names(path, fd)
    if error is not None:
        os.close(fd)
        return [item, error], None
    return [item], _Frame(path, (*frame.parts, name), info, iter(names), fd)


def _enforce_cap(stack: list[_Frame]) -> None:
    """Close the shallowest non-root descriptors beyond FD_CAP."""
    open_indexes = [i for i in range(1, len(stack)) if stack[i].fd is not None]
    excess = len(open_indexes) - max(FD_CAP, 1)
    for index in open_indexes[: max(excess, 0)]:
        os.close(stack[index].fd)  # type: ignore[arg-type]
        stack[index] = replace(stack[index], fd=None)


def _reopen_top(
    stack: list[_Frame], root_fd: int
) -> tuple[int | None, int, WalkError | None]:
    """Reopen every closed frame up to the top by an openat chain from the root.

    Closed frames always form the shallow end of the stack, so the chain
    starts at the root descriptor. Each component is opened with O_NOFOLLOW
    and checked against the identity recorded when it was listed. Returns the
    top descriptor, or the index of the first changed ancestor and its error.
    """
    parent = root_fd
    for index in range(1, len(stack)):
        frame = stack[index]
        fd, error = _open_directory(frame.path, parent, frame.parts[-1], frame.info)
        if parent != root_fd:
            os.close(parent)
        if fd is None:
            return None, index, error
        parent = fd
    return parent, 0, None


def _close_frames(frames: list[_Frame]) -> None:
    for frame in frames:
        if frame.fd is not None:
            os.close(frame.fd)


def _ensure_top_open(stack: list[_Frame], root_fd: int) -> list[WalkItem]:
    """Give the top frame a descriptor; drop changed ancestors with an error."""
    fd, index, error = _reopen_top(stack, root_fd)
    if fd is None:
        _close_frames(stack[index:])
        del stack[index:]
        return [error] if error is not None else []
    stack[-1] = replace(stack[-1], fd=fd)
    _enforce_cap(stack)
    return []


def _drain(
    stack: list[_Frame], root_fd: int, root_dev: int, prune: Prune
) -> Iterator[WalkItem]:
    while stack:
        frame = stack[-1]
        name = next(frame.names, None)
        if name is None:
            stack.pop()
            if stack and frame.fd is not None:
                os.close(frame.fd)
            continue
        if frame.fd is None:
            yield from _ensure_top_open(stack, root_fd)
            # `name` belongs to `frame`. If recovery dropped that frame (a
            # changed ancestor), the name must not be looked up anywhere else.
            if not stack or stack[-1].names is not frame.names:
                continue
        items, child = _step(stack[-1], name, root_dev, prune)
        if child is not None:
            # Push before yielding, so closing the generator releases it.
            stack.append(child)
            _enforce_cap(stack)
        yield from items


def _walk_open(
    path: str, fd: int, info: Any, root_dev: int, prune: Prune, include_start: bool
) -> Iterator[WalkItem]:
    """Walk below an already opened and verified directory; owns `fd`."""
    stack: list[_Frame] = []
    try:
        if include_start:
            yield WalkEntry(path, info)
        if is_dataless(info):
            yield WalkError(path, "scandir", "dataless", None)
            return
        names, error = _list_names(path, fd)
        if error is not None:
            yield error
            return
        stack.append(_Frame(path, (), info, iter(names), fd))
        yield from _drain(stack, fd, root_dev, prune)
    finally:
        _close_frames(stack[1:])
        os.close(fd)


def walk(root: StrPath, prune: Prune = None) -> Iterator[WalkItem]:
    """Walk root depth-first in byte order of names, never following symlinks.

    Every directory is opened with O_RDONLY | O_DIRECTORY | O_NOFOLLOW
    relative to its parent's descriptor, its identity is compared with the
    lstat recorded when it was listed, and its children are listed with
    scandir on the descriptor and examined with fstatat. A directory that was
    swapped after listing is reported with reason `changed_during_scan` and
    not walked. At most FD_CAP directory descriptors (plus the root) stay
    open; deeper ancestors are reopened by an openat chain from the root.
    Any entry on a different st_dev than root is a SkippedMount and is not
    counted or entered. A dataless directory is yielded, then reported as a
    WalkError with reason `dataless`, and never listed. The root itself is
    not yielded. Yielded paths are the root string joined with entry names.

    `prune`, when given, is called with each same-device directory entry
    before it is entered; returning True yields the entry but does not
    descend into it.
    """
    root_path = os.fspath(root)
    info = lstat(root_path)
    if not stat.S_ISDIR(info.st_mode):
        raise NotADirectoryError(
            errno.ENOTDIR, "scan root is not a directory", root_path
        )
    if is_dataless(info):
        yield WalkError(root_path, "scandir", "dataless", None)
        return
    root_fd, error = _open_directory(root_path, None, root_path, info)
    if root_fd is None:
        yield from [error] if error is not None else []
        return
    yield from _walk_open(root_path, root_fd, info, info.st_dev, prune, False)


def walk_beneath(
    root: StrPath, path: StrPath, expected: Any, prune: Prune = None
) -> Iterator[WalkItem]:
    """Walk a directory below a scan root, reached without following symlinks.

    `path` is reached by an O_NOFOLLOW openat chain from `root`, every
    component on the root's device, and must match `expected` (an lstat
    result recorded earlier, for example by discovery) by (st_dev, st_ino).
    Unlike `walk`, the start directory itself is yielded first, with its
    `fstat` result. A swapped or mismatched start is a single WalkError with
    reason `changed_during_scan`. The walk then proceeds as `walk` does,
    using the root's st_dev. Raises OSError when `path` cannot be reached for
    another reason (for example it vanished).
    """
    root_path, target = os.fspath(root), os.fspath(path)
    parts = _relative_parts(root_path, target)
    root_dev = lstat(root_path).st_dev
    try:
        fd = _open_chain(root_path, parts, target)
    except IdentityChangedError:
        yield WalkError(target, "scandir", CHANGED, None)
        return
    try:
        info = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise
    if _identity(info) != _identity(expected):
        os.close(fd)
        yield WalkError(target, "scandir", CHANGED, None)
        return
    yield from _walk_open(target, fd, info, root_dev, prune, True)


class AnchoredPath(str):
    """A path string that remembers the scan root and lstat it was found with.

    It compares, hashes, prints, and serializes exactly as the plain path, so
    outputs do not change, while consumers such as artifact sizing can reach
    it again with `walk_beneath` instead of following the path string.
    """

    root: str
    expected: Any

    def __new__(cls, path: str, root: str, expected: Any) -> Self:
        anchored = super().__new__(cls, path)
        anchored.root = root
        anchored.expected = expected
        return anchored


def _list_item(path: _BoundPath, root_dev: int) -> WalkItem:
    """Classify one listed entry; anything on a foreign device is a mount."""
    try:
        info = lstat(path)
    except OSError as error:
        return _walk_error(path, "lstat", error)
    if info.st_dev != root_dev:
        return SkippedMount(str(path))
    return WalkEntry(str(path), info)


def list_directory(path: StrPath, root_dev: int | None = None) -> list[WalkItem]:
    """List one directory's own entries in byte order of names; never descend.

    The directory is examined with `lstat` first, then opened with
    O_RDONLY | O_DIRECTORY | O_NOFOLLOW and confirmed with `fstat`; a
    directory swapped in between is reported with reason
    `changed_during_scan`. A dataless directory is never listed: the result
    is a single WalkError with reason `dataless`, as in `walk`. An unreadable
    directory gives one WalkError. Children are examined relative to the open
    descriptor, never through the path string. Any child whose `st_dev`
    differs from `root_dev` (the listed directory's own device by default)
    is a SkippedMount.
    """
    dir_path = os.fspath(path)
    try:
        info = lstat(dir_path)
    except OSError as error:
        return [_walk_error(dir_path, "lstat", error)]
    if is_dataless(info):
        return [WalkError(dir_path, "scandir", "dataless", None)]
    fd, error = _open_directory(dir_path, None, dir_path, info)
    if fd is None:
        return [error] if error is not None else []
    try:
        names, error = _list_names(dir_path, fd)
        if error is not None:
            return [error]
        device = info.st_dev if root_dev is None else root_dev
        return [
            _list_item(_BoundPath(os.path.join(dir_path, name), fd, name), device)
            for name in names
        ]
    finally:
        os.close(fd)


class NotBeneathRootError(FsReadError):
    """The path is not a plain descendant of the scan root."""

    reason = "read_error"


def _relative_parts(root_path: str, file_path: str) -> tuple[str, ...]:
    prefix = root_path if root_path.endswith("/") else root_path + "/"
    if not file_path.startswith(prefix):
        raise NotBeneathRootError(file_path, f"not beneath {root_path}: {file_path}")
    parts = tuple(file_path[len(prefix) :].split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise NotBeneathRootError(file_path, f"not a plain descendant: {file_path}")
    return parts


def _open_chain(root_path: str, parts: tuple[str, ...], file_path: str) -> int:
    """Open the directory holding the file by an O_NOFOLLOW chain from the root."""
    root_info = lstat(root_path)
    fd, error = _open_directory(root_path, None, root_path, root_info)
    if fd is None:
        if error is not None and error.reason == CHANGED:
            raise IdentityChangedError(file_path)
        reason = error.reason if error is not None else "read_error"
        raise FsReadError(file_path, f"scan root not readable ({reason}): {root_path}")
    for name in parts:
        try:
            child = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=fd,
            )
        except OSError as failure:
            os.close(fd)
            if failure.errno in _SWAP_ERRNOS:
                raise IdentityChangedError(file_path) from failure
            raise
        os.close(fd)
        fd = child
        if os.fstat(fd).st_dev != root_info.st_dev:
            os.close(fd)
            raise IdentityChangedError(file_path)
    return fd


def _open_file_at(parent: int, name: str, file_path: str, expected: Any) -> int:
    """Open a verified regular, local, non-dataless file relative to `parent`."""
    before = _entry_lstat(_Entry(name, file_path, parent))
    _require_readable(file_path, before)
    if before.st_dev != os.fstat(parent).st_dev:
        raise IdentityChangedError(file_path)
    if expected is not None and _identity(expected) != _identity(before):
        raise IdentityChangedError(file_path)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    except OSError as failure:
        if failure.errno in _SWAP_ERRNOS:
            raise IdentityChangedError(file_path) from failure
        raise
    try:
        after = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise
    if (
        _identity(after) != _identity(before)
        or not stat.S_ISREG(after.st_mode)
        or is_dataless(after)
    ):
        os.close(fd)
        raise IdentityChangedError(file_path)
    return fd


@contextmanager
def open_regular_file_beneath(
    root: StrPath, path: StrPath, expected: Any = None
) -> Iterator[int]:
    """Yield a read-only descriptor for a regular file beneath a scan root.

    Every directory between the root and the file is opened with O_NOFOLLOW
    relative to its parent, so a parent swapped for a symlink cannot redirect
    the read. The file must be regular, not dataless, and on the root's
    device; when `expected` (an lstat result from the walk) is given, the
    file's (st_dev, st_ino) must match it.
    """
    root_path, file_path = os.fspath(root), os.fspath(path)
    parts = _relative_parts(root_path, file_path)
    parent = _open_chain(root_path, parts[:-1], file_path)
    try:
        fd = _open_file_at(parent, parts[-1], file_path, expected)
    finally:
        os.close(parent)
    try:
        yield fd
    finally:
        os.close(fd)


def hash_file_beneath(
    root: StrPath, path: StrPath, algorithm: str = "sha256", expected: Any = None
) -> FileHash:
    """Hash a regular file beneath a scan root through open_regular_file_beneath."""
    with open_regular_file_beneath(root, path, expected) as fd:
        return _digest(fd, algorithm)
