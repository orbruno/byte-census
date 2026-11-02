"""`caches scan`: the largest folders in ~/Library/Caches and the tool caches.

Every immediate child folder of the Caches root is measured completely before
the display is cut to `--top`. The uv, npm, and Homebrew caches are added when
they lie outside the Caches root; a tool cache that is a child folder is
reported once, as that folder, and carries the tool's name and suggestion.
Everything here is metadata-only and read-only.
"""

import errno
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field

from byte_census import fsread
from byte_census.checks.tool_caches import (
    SUGGESTION_IDS,
    ToolCache,
    ToolResolution,
    ToolRunner,
    default_tool_runner,
    resolve_tool_caches,
)
from byte_census.checks.tree_size import InodeLedger, TreeMeasurement, measure_tree
from byte_census.command import CheckResult
from byte_census.cost import CostCounters
from byte_census.model import (
    Classification,
    CoverageEntry,
    Data,
    Finding,
    Scope,
    ScopeRoot,
    Suggestion,
    UnavailableSource,
    finding_id,
    order_findings_by_size,
)
from byte_census.paths import PathValidationError, validate_root
from byte_census.suggestions import build_check_wide

CAVEAT_CLONES = "apfs_clone_or_shared_extent"
CAVEAT_LINKS = "hard_links_merged"
ROOT_GIVEN = "~/Library/Caches"
CHILD_SOURCE = "child of ~/Library/Caches"
DEFAULT_TOP = 20


@dataclass(frozen=True)
class CachesEnvironment:
    """Everything the check reads from the machine, injectable for tests."""

    home: str
    caches_root: str
    environ: Mapping[str, str]
    run_tool: ToolRunner = default_tool_runner


def default_environment() -> CachesEnvironment:
    """The real home directory and its Library/Caches folder."""
    home = os.environ.get("HOME", "")
    root = os.path.join(home, "Library", "Caches") if home else ""
    return CachesEnvironment(home, root, dict(os.environ))


@dataclass(frozen=True)
class Candidate:
    """One measured cache folder, before ordering and truncation."""

    kind: str
    target: str
    measurement: TreeMeasurement
    tool: str | None
    location_source: str


@dataclass(frozen=True)
class Gathered:
    """Everything measured: candidates, scope, gaps, and work done."""

    candidates: tuple[Candidate, ...] = ()
    roots: tuple[ScopeRoot, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    mounts: tuple[str, ...] = ()
    entries: int = 0
    unavailable: tuple[UnavailableSource, ...] = ()
    total_allocated: int = 0
    cache_dirs: int = 0
    tool_caches: int = 0


def _coverage(path: str, error: OSError, operation: str) -> CoverageEntry:
    name = errno.errorcode.get(error.errno) if error.errno is not None else None
    return CoverageEntry(path, fsread.coverage_reason(error.errno), name, operation)


def _open_root(path: str) -> tuple[str | None, UnavailableSource | None]:
    try:
        return str(validate_root(path)), None
    except PathValidationError as error:
        reason = "not_installed" if error.reason == "not_found" else "failed"
        detail = f"{ROOT_GIVEN} could not be used: {error}"
        return None, UnavailableSource("caches", reason, detail)


@dataclass
class _Children:
    """Mutable result of listing the Caches root."""

    folders: list[tuple[str, int]] = field(default_factory=list)
    coverage: list[CoverageEntry] = field(default_factory=list)
    other_entries: int = 0


def _list_children(root: str) -> _Children:
    found = _Children()
    try:
        with os.scandir(root) as iterator:
            entries = sorted(iterator, key=lambda e: os.fsencode(e.name))
    except OSError as error:
        found.coverage.append(_coverage(root, error, "scandir"))
        return found
    for entry in entries:
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError as error:
            found.coverage.append(_coverage(entry.path, error, "lstat"))
            found.other_entries += 1
            continue
        if stat.S_ISDIR(info.st_mode):
            found.folders.append((entry.path, info.st_dev))
        else:
            found.other_entries += 1
    return found


def _measure(
    path: str, ledger: InodeLedger
) -> tuple[TreeMeasurement | None, CoverageEntry | None]:
    try:
        return measure_tree(path, ledger), None
    except OSError as error:
        return None, _coverage(path, error, "lstat")


def _is_inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _outside_tools(
    tools: ToolResolution, root: str | None, children: set[str]
) -> tuple[ToolCache, ...]:
    """Tool caches outside the root, each location once, first tool wins."""
    seen: set[str] = set()
    kept: list[ToolCache] = []
    for cache in tools.caches:
        inside = root is not None and _is_inside(cache.path, root)
        if inside or cache.path in seen or cache.path in children:
            continue
        seen.add(cache.path)
        kept.append(cache)
    return tuple(kept)


class _Collector:
    """Mutable accumulator for one run; `gathered` freezes it."""

    def __init__(self) -> None:
        self.ledger = InodeLedger()
        self.candidates: list[Candidate] = []
        self.roots: list[ScopeRoot] = []
        self.coverage: list[CoverageEntry] = []
        self.mounts: list[str] = []
        self.entries = 0

    def measure(self, kind: str, path: str, tool: ToolCache | None) -> None:
        measured, gap = _measure(path, self.ledger)
        if measured is None:
            self.entries += 1
            self.coverage.append(gap)
            return
        self.entries += measured.entries_visited
        self.coverage.extend(measured.coverage)
        self.mounts.extend(measured.skipped_mounts)
        source = tool.location_source if tool else CHILD_SOURCE
        name = tool.tool if tool else None
        self.candidates.append(Candidate(kind, path, measured, name, source))

    def measure_child(
        self, path: str, dev: int, root_dev: int, tool: ToolCache | None
    ) -> None:
        if dev != root_dev:
            self.mounts.append(path)
            self.entries += 1
            return
        self.measure("cache_dir", path, tool)

    def measure_tool(self, cache: ToolCache) -> None:
        before = len(self.candidates)
        self.measure("tool_cache", cache.path, cache)
        if len(self.candidates) > before:
            dev = fsread.lstat(cache.path).st_dev
            self.roots.append(ScopeRoot(cache.path, cache.location_source, dev))


def _gather(env: CachesEnvironment, tools: ToolResolution) -> Gathered:
    root, missing = _open_root(env.caches_root)
    listing = _children_of(root)
    col = _Collector()
    col.coverage.extend(listing.coverage)
    col.entries += listing.other_entries
    root_dev = fsread.lstat(root).st_dev if root else 0
    if root:
        col.roots.append(ScopeRoot(root, ROOT_GIVEN, root_dev))
    by_path = {c.path: c for c in reversed(tools.caches)}
    for path, dev in listing.folders:
        col.measure_child(path, dev, root_dev, by_path.get(path))
    cache_dirs = len(col.candidates)
    folders = {path for path, _ in listing.folders}
    for cache in _outside_tools(tools, root, folders):
        col.measure_tool(cache)
    return Gathered(
        candidates=tuple(col.candidates),
        roots=tuple(col.roots),
        coverage=tuple(col.coverage),
        mounts=tuple(col.mounts),
        entries=col.entries,
        unavailable=(missing,) if missing else (),
        total_allocated=col.ledger.allocated_bytes,
        cache_dirs=cache_dirs,
        tool_caches=len(col.candidates) - cache_dirs,
    )


def _children_of(root: str | None) -> _Children:
    return _list_children(root) if root else _Children()


def _finding(candidate: Candidate) -> Finding:
    measured = candidate.measurement
    caveats = (
        (CAVEAT_CLONES, CAVEAT_LINKS)
        if measured.hard_links_merged
        else (CAVEAT_CLONES,)
    )
    tool = candidate.tool
    return Finding(
        id=finding_id("cch", candidate.kind, candidate.target),
        kind=candidate.kind,
        target=candidate.target,
        logical_bytes=measured.logical_bytes,
        allocated_bytes=measured.allocated_bytes,
        reclaimable_estimate_bytes=measured.allocated_bytes,
        caveats=caveats,
        suggestion_ids=(SUGGESTION_IDS[tool],) if tool else (),
        classification=Classification(owner=tool or ""),
        details={"tool": tool, "location_source": candidate.location_source},
    )


def _suggestions(shown: tuple[Finding, ...]) -> tuple[Suggestion, ...]:
    """One check-wide suggestion per tool, relating its shown findings."""
    related: dict[str, list[str]] = {}
    for finding in shown:
        for suggestion_id in finding.suggestion_ids:
            related.setdefault(suggestion_id, []).append(finding.id)
    return tuple(build_check_wide(sid, ids) for sid, ids in related.items())


def caches_scan(env: CachesEnvironment, top: int) -> CheckResult:
    """Measure every cache folder, then keep the `top` largest for display."""
    npm_environ = {**env.environ, "HOME": env.home}
    tools = resolve_tool_caches(npm_environ, env.run_tool)
    gathered = _gather(env, tools)
    ordered = order_findings_by_size(_finding(c) for c in gathered.candidates)
    shown = ordered[:top]
    summary = {
        "cache_dir_count": gathered.cache_dirs,
        "tool_cache_count": gathered.tool_caches,
        "total_allocated_bytes": gathered.total_allocated,
        "top": top,
        "shown": len(shown),
        "truncated": len(shown) < len(ordered),
    }
    counters = CostCounters().add_entries(gathered.entries)
    for size in tools.stdout_sizes:
        counters = counters.add_subprocess_call(size)
    return CheckResult(
        data=Data(summary=summary, findings=shown, suggestions=_suggestions(shown)),
        scope=Scope(
            roots=gathered.roots,
            options={"top": top},
            skipped_mounts=gathered.mounts,
        ),
        counters=counters,
        incomplete_coverage=gathered.coverage,
        unavailable_sources=tools.unavailable + gathered.unavailable,
    )
