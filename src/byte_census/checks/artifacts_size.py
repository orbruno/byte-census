"""Sizing walk of one artifact subtree (WI-ARTIFACTS AC-02, AC-04).

Each artifact is measured by its own `fsread.walk`, which sorts names, never
follows symlinks, and never crosses `st_dev`. Inodes are keyed by
`(st_dev, st_ino)`: the displayed totals count each inode once inside the
subtree; `counted_allocated_bytes` also skips inodes that an earlier artifact
already claimed, so the summary never double counts a hard link.
"""

import errno
import stat
from collections.abc import Iterator
from dataclasses import dataclass

from byte_census import fsread
from byte_census.fsread import SkippedMount, WalkEntry, WalkError, WalkItem

InodeKey = tuple[int, int]
BLOCK = 512


@dataclass(frozen=True)
class Measure:
    """Result of sizing one artifact."""

    logical_bytes: int
    allocated_bytes: int
    counted_allocated_bytes: int
    inodes: frozenset[InodeKey]
    linked: frozenset[InodeKey]
    repeated: bool
    errors: tuple[WalkError, ...]
    mounts: tuple[SkippedMount, ...]
    visited: int
    opened: bool = True


def _error(path: str, error: OSError) -> WalkError:
    code = error.errno
    name = errno.errorcode.get(code) if code is not None else None
    return WalkError(path, "lstat", fsread.coverage_reason(code), name)


def vanished(path: str, error: OSError) -> Measure:
    """A measure for an artifact that could not be opened at all."""
    errors = (_error(path, error),)
    return Measure(
        0, 0, 0, frozenset(), frozenset(), False, errors, (), 0, opened=False
    )


class _Tally:
    """Private accumulator for one sizing walk; frozen into a Measure."""

    def __init__(self, claimed: frozenset[InodeKey]) -> None:
        self.claimed = claimed
        self.local: set[InodeKey] = set()
        self.linked: set[InodeKey] = set()
        self.errors: list[WalkError] = []
        self.mounts: list[SkippedMount] = []
        self.logical = 0
        self.allocated = 0
        self.counted = 0
        self.visited = 0
        self.repeated = False

    def add_entry(self, item: WalkEntry, is_top: bool) -> None:
        info = item.stat
        key = (info.st_dev, info.st_ino)
        self.visited += 0 if is_top else 1
        if not stat.S_ISDIR(info.st_mode) and info.st_nlink > 1:
            self.linked.add(key)
        if key in self.local:
            self.repeated = True
            return
        self.local.add(key)
        allocated = info.st_blocks * BLOCK
        self.allocated += allocated
        self.logical += info.st_size if stat.S_ISREG(info.st_mode) else 0
        self.counted += 0 if key in self.claimed else allocated

    def add_other(self, item: WalkError | SkippedMount) -> None:
        if isinstance(item, SkippedMount):
            self.mounts.append(item)
            self.visited += 1
            return
        self.errors.append(item)
        self.visited += 1 if item.operation == "lstat" else 0

    def freeze(self) -> Measure:
        return Measure(
            logical_bytes=self.logical,
            allocated_bytes=self.allocated,
            counted_allocated_bytes=self.counted,
            inodes=frozenset(self.local),
            linked=frozenset(self.linked),
            repeated=self.repeated,
            errors=tuple(self.errors),
            mounts=tuple(self.mounts),
            visited=self.visited,
        )


def _subtree_items(path: str) -> Iterator[WalkItem]:
    """The artifact itself, then everything below it.

    An `fsread.AnchoredPath` from discovery is reached again beneath its scan
    root with `fsread.walk_beneath`: no path string is followed, its identity
    must match the discovery lstat, and the scan root's device bounds the
    walk. A plain path string (direct callers) is walked as its own root.
    """
    if isinstance(path, fsread.AnchoredPath):
        yield from fsread.walk_beneath(path.root, path, path.expected)
        return
    yield WalkEntry(path, fsread.lstat(path))
    yield from fsread.walk(path)


def measure_subtree(path: str, claimed: frozenset[InodeKey]) -> Measure:
    """Size `path`; inodes in `claimed` add nothing to the counted total."""
    tally = _Tally(claimed)
    for index, item in enumerate(_subtree_items(path)):
        if isinstance(item, WalkEntry):
            tally.add_entry(item, is_top=index == 0)
        else:
            tally.add_other(item)
    return tally.freeze()
