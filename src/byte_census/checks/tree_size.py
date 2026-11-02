"""Sizing of one directory tree with a shared hard-link ledger.

`measure_tree` walks a root with the metadata-only walker (no symlinks
followed, no `st_dev` crossing) and returns the displayed totals of that
subtree: every distinct inode `(st_dev, st_ino)` counted once inside it. The
`InodeLedger` is shared by all trees of one check run, so its allocated total
is the union of everything measured and never double counts a hard link
(quantities.md, Hard links, overlap, and attribution).
"""

import stat
from dataclasses import dataclass, field
from typing import Any

from byte_census import fsread
from byte_census.model import CoverageEntry

InodeKey = tuple[int, int]


@dataclass
class InodeLedger:
    """Inodes already claimed in this run and the bytes they contribute."""

    seen: set[InodeKey] = field(default_factory=set)
    allocated_bytes: int = 0

    def claim(self, key: InodeKey, allocated: int) -> None:
        """Record an inode once; later claimants add nothing."""
        if key not in self.seen:
            self.seen.add(key)
            self.allocated_bytes += allocated


@dataclass(frozen=True)
class TreeMeasurement:
    """Displayed totals and observation gaps for one tree."""

    logical_bytes: int
    allocated_bytes: int
    entries_visited: int
    repeated: bool
    linked: frozenset[InodeKey]
    coverage: tuple[CoverageEntry, ...]
    skipped_mounts: tuple[str, ...]


class _Tally:
    """Mutable accumulator local to one `measure_tree` call."""

    def __init__(self, ledger: InodeLedger) -> None:
        self.ledger = ledger
        self.local: set[InodeKey] = set()
        self.logical = 0
        self.allocated = 0
        self.entries = 0
        self.repeated = False
        self.linked: set[InodeKey] = set()
        self.coverage: list[CoverageEntry] = []
        self.mounts: list[str] = []

    def add_inode(self, info: Any) -> None:
        key = (info.st_dev, info.st_ino)
        allocated = info.st_blocks * 512
        if key in self.local:
            self.repeated = True
            return
        self.local.add(key)
        if info.st_nlink > 1:
            self.linked.add(key)
        self.allocated += allocated
        if stat.S_ISREG(info.st_mode):
            self.logical += info.st_size
        self.ledger.claim(key, allocated)

    def add_item(self, item: fsread.WalkItem) -> None:
        if isinstance(item, fsread.WalkEntry):
            self.entries += 1
            self.add_inode(item.stat)
        elif isinstance(item, fsread.SkippedMount):
            self.entries += 1
            self.mounts.append(item.path)
        else:
            self.entries += 1 if item.operation == "lstat" else 0
            self.coverage.append(
                CoverageEntry(item.path, item.reason, item.errno_name, item.operation)
            )

    def result(self) -> TreeMeasurement:
        return TreeMeasurement(
            logical_bytes=self.logical,
            allocated_bytes=self.allocated,
            entries_visited=self.entries,
            repeated=self.repeated,
            linked=frozenset(self.linked),
            coverage=tuple(self.coverage),
            skipped_mounts=tuple(self.mounts),
        )


def measure_tree(root: str, ledger: InodeLedger) -> TreeMeasurement:
    """Measure `root` (itself included) without leaving its device.

    Raises OSError when the root cannot be examined with `lstat`.
    """
    tally = _Tally(ledger)
    tally.entries += 1
    tally.add_inode(fsread.lstat(root))
    for item in fsread.walk(root):
        tally.add_item(item)
    return tally.result()
