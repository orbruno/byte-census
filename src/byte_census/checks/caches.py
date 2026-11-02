"""`caches scan`: the largest folders in ~/Library/Caches and the tool caches.

Every immediate child folder of the Caches root is measured completely before
the display is cut to `--top`. Measurement and tool association are separate:
a tool cache outside the Caches root is measured as its own `tool_cache`
finding; a tool cache equal to the root is measured as the whole root (the
root-level files included); a tool cache inside a child folder is measured
once, as that folder, which carries the tool's name and catalog suggestion.
Several tools may share one finding. Everything here is metadata-only.
"""

import errno
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from byte_census import fsread
from byte_census.checks.tool_caches import (
    SUGGESTION_IDS,
    ToolCache,
    ToolResolution,
    ToolRunner,
    default_tool_runner,
    resolve_tool_caches,
)
from byte_census.checks.tree_size import (
    InodeKey,
    InodeLedger,
    TreeMeasurement,
    UnreachableStartError,
    measure_tree,
    measure_tree_beneath,
)
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
    tools: tuple[ToolCache, ...] = ()


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

    folders: list[str] = field(default_factory=list)
    listed: dict[str, Any] = field(default_factory=dict)
    coverage: list[CoverageEntry] = field(default_factory=list)
    mounts: list[str] = field(default_factory=list)
    other_entries: int = 0


def _list_children(root: str) -> _Children:
    """Sort the root's own entries into folders, mounts, gaps, and the rest."""
    found = _Children()
    for item in fsread.list_directory(root):
        if isinstance(item, fsread.WalkError):
            found.coverage.append(
                CoverageEntry(item.path, item.reason, item.errno_name, item.operation)
            )
            found.other_entries += 1 if item.operation == "lstat" else 0
        elif isinstance(item, fsread.SkippedMount):
            found.mounts.append(item.path)
            found.other_entries += 1
        elif item.kind == "directory":
            found.folders.append(item.path)
            found.listed[item.path] = item.stat
        else:
            found.other_entries += 1
    return found


Beneath = tuple[str, Any]


def _measure(
    path: str, ledger: InodeLedger, beneath: Beneath | None = None
) -> tuple[TreeMeasurement | None, CoverageEntry | None]:
    """Measure one unit. A folder listed in the Caches root (`beneath` is the
    root and its listing lstat) is reached again beneath that root, never by
    its path string; other units are walk start directories."""
    try:
        if beneath is None:
            return measure_tree(path, ledger), None
        root, expected = beneath
        return measure_tree_beneath(root, path, expected, ledger), None
    except UnreachableStartError as refused:
        item = refused.item
        entry = CoverageEntry(item.path, item.reason, item.errno_name, item.operation)
        return None, entry
    except OSError as error:
        return None, _coverage(path, error, "lstat")


def _is_inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _host_of(path: str, units: Sequence[str]) -> str | None:
    """The innermost measured unit that contains `path`, if any."""
    inside = [unit for unit in units if _is_inside(path, unit)]
    return max(inside, key=len) if inside else None


def _tool_units(
    tools: Sequence[ToolCache], root: str | None, folders: Sequence[str]
) -> tuple[list[str], list[str]]:
    """Return (units to measure for tools, all units known to host tools).

    The root is a unit when a tool equals it. A tool outside the root becomes a
    unit unless an already chosen unit contains it.
    """
    units = list(folders)
    extra: list[str] = []
    if root is not None and any(t.path == root for t in tools):
        units.append(root)
        extra.append(root)
    for cache in sorted(tools, key=lambda t: (len(t.path), t.path)):
        outside = root is None or not _is_inside(cache.path, root)
        if outside and _host_of(cache.path, units) is None:
            units.append(cache.path)
            extra.append(cache.path)
    return extra, units


def _hosting(
    tools: Sequence[ToolCache], units: Sequence[str]
) -> dict[str, tuple[ToolCache, ...]]:
    """Tools by host unit, in tool order; a tool without a host is dropped."""
    hosted: dict[str, list[ToolCache]] = {}
    for cache in tools:
        host = _host_of(cache.path, units)
        if host is not None:
            hosted.setdefault(host, []).append(cache)
    return {unit: tuple(found) for unit, found in hosted.items()}


class _Collector:
    """Mutable accumulator for one run."""

    def __init__(self) -> None:
        self.ledger = InodeLedger()
        self.candidates: list[Candidate] = []
        self.roots: list[ScopeRoot] = []
        self.coverage: list[CoverageEntry] = []
        self.mounts: list[str] = []
        self.entries = 0

    def measure(
        self,
        kind: str,
        path: str,
        tools: tuple[ToolCache, ...],
        beneath: Beneath | None = None,
    ) -> bool:
        measured, gap = _measure(path, self.ledger, beneath)
        if measured is None:
            self.entries += 1
            self.coverage.append(gap)
            return False
        self.entries += measured.entries_visited
        self.coverage.extend(measured.coverage)
        self.mounts.extend(measured.skipped_mounts)
        self.candidates.append(Candidate(kind, path, measured, tools))
        return True

    def measure_tool_unit(self, path: str, tools: tuple[ToolCache, ...]) -> None:
        try:
            device = fsread.lstat(path).st_dev
        except OSError as error:
            self.entries += 1
            self.coverage.append(_coverage(path, error, "lstat"))
            return
        if self.measure("tool_cache", path, tools) and tools:
            self.roots.append(ScopeRoot(path, tools[0].location_source, device))


def _gather(env: CachesEnvironment, tools: ToolResolution) -> Gathered:
    root, missing = _open_root(env.caches_root)
    listing = _list_children(root) if root else _Children()
    col = _Collector()
    col.coverage.extend(listing.coverage)
    col.mounts.extend(listing.mounts)
    col.entries += listing.other_entries
    if root:
        device = fsread.lstat(root).st_dev
        col.roots.append(ScopeRoot(root, ROOT_GIVEN, device))
    extra, units = _tool_units(tools.caches, root, listing.folders)
    hosted = _hosting(tools.caches, units)
    for path in listing.folders:
        beneath = (root, listing.listed[path]) if root else None
        col.measure("cache_dir", path, hosted.get(path, ()), beneath)
    cache_dirs = len(col.candidates)
    for path in extra:
        col.measure_tool_unit(path, hosted.get(path, ()))
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


def _shared_links(candidates: Sequence[Candidate]) -> frozenset[InodeKey]:
    """Multi-name inodes seen by more than one finding, whatever the order."""
    seen = Counter(key for c in candidates for key in c.measurement.linked)
    return frozenset(key for key, count in seen.items() if count > 1)


def _details(candidate: Candidate) -> dict[str, object]:
    tools = candidate.tools
    if not tools:
        return {"tool": None, "location_source": CHILD_SOURCE}
    details: dict[str, object] = {
        "tool": tools[0].tool,
        "location_source": tools[0].location_source,
    }
    if len(tools) > 1:
        details["other_tools"] = [
            {"tool": t.tool, "location_source": t.location_source} for t in tools[1:]
        ]
    if any(t.path != candidate.target for t in tools):
        details["tool_locations"] = [t.path for t in tools]
    uncertain = [t.uncertain for t in tools if t.uncertain]
    if uncertain:
        details["location_uncertain"] = "; ".join(uncertain)
    return details


def _finding(candidate: Candidate, shared: frozenset[InodeKey]) -> Finding:
    measured = candidate.measurement
    merged = measured.repeated or bool(measured.linked & shared)
    caveats = (CAVEAT_CLONES, CAVEAT_LINKS) if merged else (CAVEAT_CLONES,)
    tools = candidate.tools
    return Finding(
        id=finding_id("cch", candidate.kind, candidate.target),
        kind=candidate.kind,
        target=candidate.target,
        logical_bytes=measured.logical_bytes,
        allocated_bytes=measured.allocated_bytes,
        reclaimable_estimate_bytes=measured.allocated_bytes,
        caveats=caveats,
        suggestion_ids=tuple(SUGGESTION_IDS[t.tool] for t in tools),
        classification=Classification(owner=tools[0].tool if tools else ""),
        details=_details(candidate),
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
    shared = _shared_links(gathered.candidates)
    ordered = order_findings_by_size(_finding(c, shared) for c in gathered.candidates)
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
        incomplete_coverage=tools.coverage + gathered.coverage,
        unavailable_sources=tools.unavailable + gathered.unavailable,
    )
