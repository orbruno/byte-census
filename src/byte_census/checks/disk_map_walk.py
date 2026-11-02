"""Single-process traversal for `disk map` (quantities.md).

Each walked scope (a root, or a category or tool cache outside every earlier
scope) is traversed once with `fsread.list_directory` (no symlinks followed,
no `st_dev` crossing). Subtrees of earlier walked scopes are pruned, so walks
never overlap. One pass feeds several views: the scope itself, every
declared scope inside it (found by directory identity, not by spelling), and
the first-level folders of each root view.

`Ledger` is the run-wide identity ledger. Every inode is claimed once, by the
first claimant in precedence order, so an inode reached twice through any
alias is counted once and the sum of counted contributions is the allocated
size of the union of everything walked.
"""

import stat
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from byte_census import fsread
from byte_census.model import CoverageEntry

InodeKey = tuple[int, int]
ViewKey = tuple[str, str]  # (kind, path)
LinkBytes = tuple[InodeKey, int, int]  # (inode, allocated, logical)
FIRST_LEVEL_VIEW = "first_level"
TREE_NODE = "tree_node"
LARGE_FILE_LIMIT = 20


def is_multi_link(info: Any) -> bool:
    return not stat.S_ISDIR(info.st_mode) and info.st_nlink > 1


def allocated_of(info: Any) -> int:
    return info.st_blocks * 512


def is_sparse(info: Any) -> bool:
    return stat.S_ISREG(info.st_mode) and info.st_size > allocated_of(info)


@dataclass
class Ledger:
    """Run-wide inode claims and the names each hard-linked inode was seen as."""

    claimed: dict[int, set[int]] = field(default_factory=dict)
    allocated_bytes: int = 0
    link_views: dict[InodeKey, set[ViewKey]] = field(default_factory=dict)
    link_visits: dict[InodeKey, int] = field(default_factory=dict)

    def claim(self, info: Any) -> int:
        """Allocated bytes this claim adds; 0 when an earlier claim had it."""
        inodes = self.claimed.setdefault(info.st_dev, set())
        if info.st_ino in inodes:
            return 0
        inodes.add(info.st_ino)
        self.allocated_bytes += allocated_of(info)
        return allocated_of(info)

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
class ViewSpec:
    """A declared scope shown inside a walk, identified by its directory."""

    kind: str
    path: str
    identity: InodeKey
    first_level: bool = False
    large_files: bool = False


@dataclass(frozen=True)
class LargeFile:
    """A regular file above the large-file threshold."""

    path: str
    root: str
    logical_bytes: int
    allocated_bytes: int
    inode: InodeKey


@dataclass(frozen=True)
class ViewTotals:
    """Displayed totals of one view, with what unions and caveats need."""

    kind: str
    path: str
    owner: str
    logical_bytes: int
    allocated_bytes: int
    sparse: bool = False
    observed: bool = True
    links: tuple[LinkBytes, ...] = ()
    large_files: tuple[LargeFile, ...] = ()

    @property
    def key(self) -> ViewKey:
        return (self.kind, self.path)


def large_file_order(item: LargeFile) -> tuple[int, str]:
    """Selection key: logical bytes descending, then path."""
    return (-item.logical_bytes, item.path)


def select_large(items: Iterable[LargeFile]) -> list[LargeFile]:
    return sorted(items, key=large_file_order)[:LARGE_FILE_LIMIT]


class _View:
    """Mutable accumulator for one view during one walk."""

    def __init__(self, kind: str, path: str, owner: str, spec: ViewSpec) -> None:
        self.kind, self.path, self.owner, self.spec = kind, path, owner, spec
        self.links: dict[InodeKey, tuple[int, int]] = {}
        self.logical = 0
        self.allocated = 0
        self.sparse = False
        self.observed = False
        self.large: list[LargeFile] = []

    def add(self, info: Any) -> None:
        logical = info.st_size if stat.S_ISREG(info.st_mode) else 0
        if is_multi_link(info):
            key = (info.st_dev, info.st_ino)
            if key in self.links:
                return
            self.links[key] = (allocated_of(info), logical)
        self.allocated += allocated_of(info)
        self.logical += logical
        self.sparse = self.sparse or is_sparse(info)

    def kind_key(self) -> ViewKey:
        return (self.kind, self.path)

    def add_large(self, item: LargeFile) -> None:
        self.large.append(item)
        if len(self.large) > 4 * LARGE_FILE_LIMIT:
            self.large = select_large(self.large)

    def totals(self) -> ViewTotals:
        return ViewTotals(
            kind=self.kind,
            path=self.path,
            owner=self.owner,
            logical_bytes=self.logical,
            allocated_bytes=self.allocated,
            sparse=self.sparse,
            observed=self.observed,
            links=tuple((k, a, lg) for k, (a, lg) in sorted(self.links.items())),
            large_files=tuple(select_large(self.large)),
        )


@dataclass(frozen=True)
class ScopeWalk:
    """Everything one walk of one scope measured."""

    path: str
    views: tuple[ViewTotals, ...]
    counted_allocated_bytes: int
    entries_visited: int
    coverage: tuple[CoverageEntry, ...]
    skipped_mounts: tuple[str, ...]
    tree_nodes: tuple[ViewTotals, ...] = ()


def walk_pruned(
    root: str, root_dev: int, prune: Callable[[fsread.WalkEntry], bool]
) -> Iterator[fsread.WalkItem]:
    """Depth-first walk in byte order of names; pruned directories vanish.

    The walk is fsread's descriptor-relative walk, so no directory below the
    root is reached through its path string. `root_dev` is the root's own
    device, which the walk records itself. A root that is not a directory
    gives the single error `list_directory` reports for it.
    """
    pruned: set[str] = set()

    def skip(entry: fsread.WalkEntry) -> bool:
        if prune(entry):
            pruned.add(entry.path)
            return True
        return False

    items = fsread.walk(root, prune=skip)
    try:
        first = next(items)
    except StopIteration:
        return
    except NotADirectoryError:
        yield from fsread.list_directory(root, root_dev)
        return
    yield from _unpruned(first, items, pruned)


def _unpruned(
    first: fsread.WalkItem, rest: Iterator[fsread.WalkItem], pruned: set[str]
) -> Iterator[fsread.WalkItem]:
    """Drop the entries of pruned directories; everything else passes."""
    if not _is_pruned(first, pruned):
        yield first
    for item in rest:
        if not _is_pruned(item, pruned):
            yield item


def _is_pruned(item: fsread.WalkItem, pruned: set[str]) -> bool:
    return isinstance(item, fsread.WalkEntry) and item.path in pruned


class _WalkTally:
    """Mutable accumulator for one walked scope; `result` freezes it."""

    def __init__(
        self, scope: ViewSpec, inner: tuple[ViewSpec, ...], tree_depth: int = 0
    ) -> None:
        self.tree_depth = tree_depth
        self.tree: dict[tuple[str, str], _View] = {}
        self.scope = _View(scope.kind, scope.path, scope.path, scope)
        self.scope.observed = True
        self.pending: dict[InodeKey, list[ViewSpec]] = {}
        for spec in inner:
            self.pending.setdefault(spec.identity, []).append(spec)
        self.active: list[tuple[str, _View]] = [(scope.path, self.scope)]
        self.first: dict[str, _View] = {}
        self.counted = 0
        self.entries = 0
        self.coverage: list[CoverageEntry] = []
        self.mounts: list[str] = []
        self.inner_views: list[_View] = []

    def _activate(self, path: str, info: Any) -> None:
        for spec in self.pending.pop((info.st_dev, info.st_ino), []):
            view = _View(spec.kind, spec.path, spec.path, spec)
            view.observed = True
            self.inner_views.append(view)
            self.active.append((path, view))

    def _containing(self, path: str) -> list[tuple[str, _View]]:
        return [
            (prefix, view)
            for prefix, view in self.active
            if path == prefix or path.startswith(prefix.rstrip("/") + "/")
        ]

    def _first_level(
        self, prefix: str, view: _View, parts: list[str], is_dir: bool
    ) -> _View | None:
        key = prefix.rstrip("/") + "/" + parts[0]
        if len(parts) == 1 and is_dir:
            target = view.path.rstrip("/") + "/" + parts[0]
            self.first[key] = _View(FIRST_LEVEL_VIEW, target, view.path, view.spec)
            self.first[key].observed = True
        return self.first.get(key)

    def _tree_nodes(self, view: _View, parts: list[str], is_dir: bool) -> list[_View]:
        """Tree folders of a root view holding this entry, down to the depth.

        A folder's node is created when the folder itself is visited (walks
        are pre-order), so its ancestors' nodes always exist already.
        """
        found: list[_View] = []
        for level in range(1, min(self.tree_depth, len(parts)) + 1):
            relative = "/".join(parts[:level])
            key = (view.path, relative)
            if level == len(parts) and is_dir:
                target = view.path.rstrip("/") + "/" + relative
                self.tree[key] = _View(TREE_NODE, target, view.path, view.spec)
            node = self.tree.get(key)
            if node is not None:
                found.append(node)
        return found

    def _subviews(
        self, prefix: str, view: _View, path: str, is_dir: bool
    ) -> list[_View]:
        """First-level and tree views of a root view that hold this entry."""
        if path == prefix or not view.spec.first_level:
            return []
        parts = path[len(prefix.rstrip("/")) + 1 :].split("/")
        first = self._first_level(prefix, view, parts, is_dir)
        found = [first] if first is not None else []
        return found + self._tree_nodes(view, parts, is_dir)

    def views_for(self, path: str, info: Any) -> list[_View]:
        is_dir = stat.S_ISDIR(info.st_mode)
        if is_dir:
            self._activate(path, info)
        views: list[_View] = []
        for prefix, view in self._containing(path):
            views.append(view)
            views.extend(self._subviews(prefix, view, path, is_dir))
        return views

    def add_inode(self, path: str, info: Any, large_min: int, ledger: Ledger) -> None:
        self.entries += 1
        views = self.views_for(path, info)
        for view in views:
            view.add(info)
        self.counted += ledger.claim(info)
        if is_multi_link(info):
            ledger.record_link(info, (v.kind_key() for v in views))
        if stat.S_ISREG(info.st_mode) and info.st_size > large_min:
            self._add_large(path, info, views)

    def _add_large(self, path: str, info: Any, views: list[_View]) -> None:
        """Offer the file to the selection buffer of every root view holding it."""
        inode = (info.st_dev, info.st_ino)
        for view in views:
            if view.kind not in (FIRST_LEVEL_VIEW, TREE_NODE) and view.spec.large_files:
                size, allocated = info.st_size, allocated_of(info)
                view.add_large(LargeFile(path, view.path, size, allocated, inode))

    def add_item(self, item: fsread.WalkItem) -> None:
        if isinstance(item, fsread.SkippedMount):
            self.entries += 1
            self.mounts.append(item.path)
        else:
            self.entries += 1 if item.operation == "lstat" else 0
            self.coverage.append(
                CoverageEntry(item.path, item.reason, item.errno_name, item.operation)
            )

    def result(self) -> ScopeWalk:
        unseen = [
            _View(s.kind, s.path, s.path, s)
            for specs in self.pending.values()
            for s in specs
        ]
        views = [self.scope, *self.inner_views, *unseen, *self.first.values()]
        return ScopeWalk(
            path=self.scope.path,
            views=tuple(v.totals() for v in views),
            counted_allocated_bytes=self.counted,
            entries_visited=self.entries,
            coverage=tuple(self.coverage),
            skipped_mounts=tuple(self.mounts),
            tree_nodes=tuple(node.totals() for node in self.tree.values()),
        )


@dataclass(frozen=True)
class WalkRequest:
    """One scope to walk: itself, the scopes shown inside it, and prunes.

    `tree_depth` is how many folder levels below each root view the walk
    also totals for the folder tree (0: none).
    """

    scope: ViewSpec
    inner: tuple[ViewSpec, ...] = ()
    excluded: frozenset[InodeKey] = frozenset()
    tree_depth: int = 0


def walk_scope(request: WalkRequest, ledger: Ledger, large_min_bytes: int) -> ScopeWalk:
    """Walk one scope (itself included) and measure every view inside it.

    Raises OSError when the scope cannot be examined with `lstat`.
    """
    tally = _WalkTally(request.scope, request.inner, request.tree_depth)
    root = request.scope.path
    info = fsread.lstat(root)
    tally.add_inode(root, info, large_min_bytes, ledger)

    def prune(entry: fsread.WalkEntry) -> bool:
        return (entry.stat.st_dev, entry.stat.st_ino) in request.excluded

    for item in walk_pruned(root, info.st_dev, prune):
        if isinstance(item, fsread.WalkEntry):
            tally.add_inode(item.path, item.stat, large_min_bytes, ledger)
        else:
            tally.add_item(item)
    return tally.result()


def unreached_walk(request: WalkRequest, gap: CoverageEntry) -> ScopeWalk:
    """A scope that could not be examined: every view in it is unobserved."""
    views = (
        ViewTotals(spec.kind, spec.path, spec.path, 0, 0, observed=False)
        for spec in (request.scope, *request.inner)
    )
    return ScopeWalk(request.scope.path, tuple(views), 0, 1, (gap,), ())
