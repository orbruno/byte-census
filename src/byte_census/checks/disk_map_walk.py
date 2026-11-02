"""Single-process traversal for `disk map` (quantities.md).

Each walked root is traversed once with `fsread.walk` (no symlinks followed,
no `st_dev` crossing). One pass feeds several views: the root itself, each
first-level folder, and every nested root (with its own first-level folders).
A view's displayed totals count each distinct inode once inside that view.

`Ledger` holds the run-wide claims: it answers which root counts an inode
first, so the sum of counted contributions is the union of everything walked.
Walks never overlap (nested roots are not walked again, and later claimants
such as categories must not descend into roots), so only inodes with more
than one name can be seen twice; only those are remembered, which keeps
memory proportional to hard-linked files rather than to all entries.
"""

import stat
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from byte_census import fsread
from byte_census.checks.disk_map_roots import is_inside
from byte_census.model import CoverageEntry

InodeKey = tuple[int, int]
ViewKey = tuple[str, str]  # (kind, path)
ROOT_VIEW = "root_total"
FIRST_LEVEL_VIEW = "first_level"
LARGE_FILE_LIMIT = 20


def _is_multi_link(info: Any) -> bool:
    return not stat.S_ISDIR(info.st_mode) and info.st_nlink > 1


def _allocated(info: Any) -> int:
    return info.st_blocks * 512


@dataclass
class Ledger:
    """Run-wide inode claims and the names each hard-linked inode was seen as."""

    claimed: set[InodeKey] = field(default_factory=set)
    allocated_bytes: int = 0
    link_views: dict[InodeKey, set[ViewKey]] = field(default_factory=dict)
    link_visits: dict[InodeKey, int] = field(default_factory=dict)

    def claim(self, info: Any) -> int:
        """Allocated bytes this claim adds; 0 when an earlier claim had it."""
        if _is_multi_link(info):
            key = (info.st_dev, info.st_ino)
            if key in self.claimed:
                return 0
            self.claimed.add(key)
        self.allocated_bytes += _allocated(info)
        return _allocated(info)

    def record_link(self, info: Any, views: Iterable[ViewKey]) -> None:
        """Remember one name of a hard-linked inode and the views showing it."""
        key = (info.st_dev, info.st_ino)
        self.link_visits[key] = self.link_visits.get(key, 0) + 1
        self.link_views.setdefault(key, set()).update(views)

    def merged(self, key: InodeKey) -> bool:
        return self.link_visits.get(key, 0) > 1

    def merged_views(self) -> frozenset[ViewKey]:
        """Views holding an inode that was seen under more than one name."""
        return frozenset(
            view
            for key, views in self.link_views.items()
            if self.merged(key)
            for view in views
        )


@dataclass(frozen=True)
class ViewTotals:
    """Displayed totals of one view."""

    kind: str
    path: str
    owner: str
    logical_bytes: int
    allocated_bytes: int

    @property
    def key(self) -> ViewKey:
        return (self.kind, self.path)


@dataclass(frozen=True)
class LargeFile:
    """A regular file above the large-file threshold."""

    path: str
    root: str
    logical_bytes: int
    allocated_bytes: int
    inode: InodeKey


@dataclass(frozen=True)
class RootWalk:
    """Everything one walk of one root measured."""

    root: str
    views: tuple[ViewTotals, ...]
    large_files: tuple[LargeFile, ...]
    counted_allocated_bytes: int
    entries_visited: int
    coverage: tuple[CoverageEntry, ...]
    skipped_mounts: tuple[str, ...]


class _View:
    """Mutable accumulator for one view during one walk."""

    def __init__(self, kind: str, path: str, owner: str) -> None:
        self.kind, self.path, self.owner = kind, path, owner
        self.links: set[InodeKey] = set()
        self.logical = 0
        self.allocated = 0

    def add(self, info: Any) -> None:
        if _is_multi_link(info):
            key = (info.st_dev, info.st_ino)
            if key in self.links:
                return
            self.links.add(key)
        self.allocated += _allocated(info)
        if stat.S_ISREG(info.st_mode):
            self.logical += info.st_size

    def totals(self) -> ViewTotals:
        return ViewTotals(
            self.kind, self.path, self.owner, self.logical, self.allocated
        )


def large_file_order(item: LargeFile) -> tuple[int, str]:
    """Selection key: logical bytes descending, then path."""
    return (-item.logical_bytes, item.path)


class _RootTally:
    """Mutable accumulator for one walked root; `result` freezes it."""

    def __init__(
        self, root: str, nested: tuple[str, ...], ledger: Ledger, large_min: int
    ) -> None:
        self.root, self.nested, self.ledger = root, nested, ledger
        self.large_min = large_min
        self.roots = {path: _View(ROOT_VIEW, path, path) for path in (root, *nested)}
        self.first: dict[str, _View] = {}
        self.large: list[LargeFile] = []
        self.counted = 0
        self.entries = 0
        self.coverage: list[CoverageEntry] = []
        self.mounts: list[str] = []

    def _first_level(self, owner: str, path: str, is_dir: bool) -> _View | None:
        first = path[len(owner.rstrip("/")) + 1 :].split("/", 1)[0]
        key = owner.rstrip("/") + "/" + first
        if key == path and is_dir:
            self.first[key] = _View(FIRST_LEVEL_VIEW, key, owner)
        return self.first.get(key)

    def _views_for(self, path: str, is_dir: bool) -> list[_View]:
        views = [self.roots[self.root]]
        owners = [self.root]
        for nested in self.nested:
            if is_inside(path, nested):
                views.append(self.roots[nested])
                if path != nested:
                    owners.append(nested)
        for owner in owners:
            view = self._first_level(owner, path, is_dir)
            if view is not None:
                views.append(view)
        return views

    def add_inode(self, path: str, info: Any) -> None:
        self.entries += 1
        is_dir = stat.S_ISDIR(info.st_mode)
        views = (
            self._views_for(path, is_dir)
            if path != self.root
            else [self.roots[self.root]]
        )
        for view in views:
            view.add(info)
        self.counted += self.ledger.claim(info)
        if _is_multi_link(info):
            self.ledger.record_link(info, ((v.kind, v.path) for v in views))
        if stat.S_ISREG(info.st_mode) and info.st_size > self.large_min:
            self._add_large(path, info)

    def _add_large(self, path: str, info: Any) -> None:
        inode = (info.st_dev, info.st_ino)
        self.large.append(
            LargeFile(path, self.root, info.st_size, _allocated(info), inode)
        )
        if len(self.large) > 4 * LARGE_FILE_LIMIT:
            self.large = sorted(self.large, key=large_file_order)[:LARGE_FILE_LIMIT]

    def add_item(self, item: fsread.WalkItem) -> None:
        if isinstance(item, fsread.WalkEntry):
            self.add_inode(item.path, item.stat)
        elif isinstance(item, fsread.SkippedMount):
            self.entries += 1
            self.mounts.append(item.path)
        else:
            self.entries += 1 if item.operation == "lstat" else 0
            self.coverage.append(
                CoverageEntry(item.path, item.reason, item.errno_name, item.operation)
            )

    def result(self) -> RootWalk:
        views = [v.totals() for v in (*self.roots.values(), *self.first.values())]
        return RootWalk(
            root=self.root,
            views=tuple(views),
            large_files=tuple(
                sorted(self.large, key=large_file_order)[:LARGE_FILE_LIMIT]
            ),
            counted_allocated_bytes=self.counted,
            entries_visited=self.entries,
            coverage=tuple(self.coverage),
            skipped_mounts=tuple(self.mounts),
        )


def walk_root(
    root: str, nested: tuple[str, ...], ledger: Ledger, large_min_bytes: int
) -> RootWalk:
    """Walk `root` once (itself included) and measure every view inside it.

    Raises OSError when the root cannot be examined with `lstat`.
    """
    tally = _RootTally(root, nested, ledger, large_min_bytes)
    tally.add_inode(root, fsread.lstat(root))
    for item in fsread.walk(root):
        tally.add_item(item)
    return tally.result()
