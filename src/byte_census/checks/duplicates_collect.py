"""Collection stage of `duplicates scan`: walk the roots, merge hard links.

Metadata only; no file content is read here. Each regular file is keyed by
`(st_dev, st_ino)`, so every name of one inode becomes one candidate
(quantities.md, hard links). Empty files, files below `--min-size`, and
non-regular entries are not candidates. Dataless files are never opened;
when they would otherwise be candidates they are listed in
`incomplete_coverage`.
"""

import errno
import os
import stat
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from byte_census import fsread
from byte_census.model import CoverageEntry

LEFT = "path"
RIGHT = "compare"


@dataclass(frozen=True)
class Inode:
    """One distinct file: its names, the roots it was seen under, its lstat."""

    key: tuple[int, int]
    names: tuple[str, ...]
    sides: frozenset[str]
    size: int
    allocated: int
    mtime_ns: int

    @property
    def primary(self) -> str:
        """Decision: the shallowest name, then code-point order."""
        return min(self.names, key=lambda name: (name.count("/"), name))

    @property
    def other_names(self) -> tuple[str, ...]:
        return tuple(sorted(name for name in self.names if name != self.primary))


@dataclass(frozen=True)
class RootSpec:
    """A resolved root and which side of `--compare` it belongs to."""

    path: str
    side: str


@dataclass(frozen=True)
class Collection:
    """Candidates and what the collection walk observed."""

    inodes: tuple[Inode, ...]
    entries_visited: int
    coverage: tuple[CoverageEntry, ...]
    skipped_mounts: tuple[str, ...]


def _walk_error(path: str, operation: str, error: OSError) -> fsread.WalkError:
    code = error.errno
    name = errno.errorcode.get(code) if code is not None else None
    return fsread.WalkError(path, operation, fsread.coverage_reason(code), name)


def _top_level(root: str) -> Iterator[fsread.WalkItem]:
    """List root's own entries in byte order of names, without descending."""
    try:
        with os.scandir(root) as iterator:
            names = sorted((entry.name for entry in iterator), key=os.fsencode)
    except OSError as error:
        yield _walk_error(root, "scandir", error)
        return
    for name in names:
        path = os.path.join(root, name)
        try:
            yield fsread.WalkEntry(path, fsread.lstat(path))
        except OSError as error:
            yield _walk_error(path, "lstat", error)


def _items(root: str, recursive: bool) -> Iterator[fsread.WalkItem]:
    return fsread.walk(root) if recursive else _top_level(root)


def _is_candidate(info: Any, min_size: int) -> bool:
    return stat.S_ISREG(info.st_mode) and info.st_size > 0 and info.st_size >= min_size


@dataclass(frozen=True)
class _Seen:
    """Raw observations of one walk, before inodes are merged."""

    files: tuple[tuple[str, str, Any], ...]
    entries: int
    coverage: tuple[CoverageEntry, ...]
    mounts: tuple[str, ...]


def _coverage(item: fsread.WalkError) -> CoverageEntry:
    return CoverageEntry(item.path, item.reason, item.errno_name, item.operation)


def _observe(spec: RootSpec, recursive: bool, min_size: int) -> _Seen:
    files: list[tuple[str, str, Any]] = []
    coverage: list[CoverageEntry] = []
    mounts: list[str] = []
    entries = 0
    for item in _items(spec.path, recursive):
        if isinstance(item, fsread.WalkError):
            coverage.append(_coverage(item))
            entries += 1 if item.operation == "lstat" else 0
            continue
        entries += 1
        if isinstance(item, fsread.SkippedMount):
            mounts.append(item.path)
        elif _is_candidate(item.stat, min_size):
            if item.is_dataless:
                coverage.append(CoverageEntry(item.path, "dataless", None, "lstat"))
            else:
                files.append((item.path, spec.side, item.stat))
    return _Seen(tuple(files), entries, tuple(coverage), tuple(mounts))


def _merge(files: Iterable[tuple[str, str, Any]]) -> tuple[Inode, ...]:
    """One Inode per (st_dev, st_ino); names and sides are unions."""
    names: dict[tuple[int, int], set[str]] = {}
    sides: dict[tuple[int, int], set[str]] = {}
    infos: dict[tuple[int, int], Any] = {}
    for path, side, info in files:
        key = (info.st_dev, info.st_ino)
        names.setdefault(key, set()).add(path)
        sides.setdefault(key, set()).add(side)
        infos.setdefault(key, info)
    inodes = (
        Inode(
            key=key,
            names=tuple(sorted(names[key])),
            sides=frozenset(sides[key]),
            size=info.st_size,
            allocated=info.st_blocks * 512,
            mtime_ns=info.st_mtime_ns,
        )
        for key, info in infos.items()
    )
    return tuple(sorted(inodes, key=lambda inode: inode.primary))


def collect(roots: Sequence[RootSpec], recursive: bool, min_size: int) -> Collection:
    """Walk every root once and merge hard links across all of them."""
    seen = [_observe(spec, recursive, min_size) for spec in roots]
    return Collection(
        inodes=_merge(f for part in seen for f in part.files),
        entries_visited=sum(part.entries for part in seen),
        coverage=tuple(entry for part in seen for entry in part.coverage),
        skipped_mounts=tuple(mount for part in seen for mount in part.mounts),
    )
