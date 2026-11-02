"""`disk map`: where the data volume's used space is.

Steps: canonicalize every `--scan-root` to the data volume (exit 3
otherwise), read `df -k /System/Volumes/Data` (exit 4 when it fails), read
the optional system sources, locate the categories and tool caches (unless
`--skip-categories`), place every scope in attribution precedence, walk each
walked scope once in a single process with one shared identity ledger, then
build findings from complete totals and cut the display to `--top` last.

Seam (later Work Item, not implemented here): WI-DISK-MAP-TREE adds the
`tree` section in `_extra_sections`.
"""

import errno
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from byte_census import fsread, runner
from byte_census.checks.disk_map_categories import (
    CategorySpec,
    Located,
    default_categories,
    locate_categories,
    locate_tool_caches,
)
from byte_census.checks.disk_map_findings import (
    Unit,
    first_level,
    large_files,
    ordered,
    unit,
)
from byte_census.checks.disk_map_reconcile import (
    Contribution,
    DfUsage,
    parse_df,
    read_df,
    reconciliation,
)
from byte_census.checks.disk_map_roots import (
    DataVolume,
    Lstat,
    canonical_root,
    merge_roots,
)
from byte_census.checks.disk_map_scopes import (
    ROOT,
    DeclaredScope,
    Placement,
    displayed_totals,
    plan_scopes,
    walk_plans,
)
from byte_census.checks.disk_map_see_check import SeeCheckRules
from byte_census.checks.disk_map_system import Run, SystemContext, read_system
from byte_census.checks.disk_map_walk import (
    Ledger,
    ScopeWalk,
    ViewTotals,
    WalkRequest,
    unreached_walk,
    walk_scope,
)
from byte_census.command import CheckResult
from byte_census.cost import CostCounters
from byte_census.errors import ValidationError
from byte_census.fsread import coverage_reason
from byte_census.model import CoverageEntry, Data, Scope, ScopeRoot

__all__ = [
    "DATA_VOLUME_MOUNT",
    "DataVolume",
    "DiskMapEnvironment",
    "SeeCheckRules",
    "ValidationError",
    "canonical_root",
    "default_df_runner",
    "default_environment",
    "disk_map",
    "parse_df",
]

DATA_VOLUME_MOUNT = "/System/Volumes/Data"
DEFAULT_TOP = 30
DEFAULT_LARGE_FILE_MIN_MB = 500
MIB = 1024 * 1024


def default_df_runner(argv: Sequence[str]) -> runner.RunResult:
    """The allowlisted runner, for df and every optional source."""
    return runner.run(argv)


@dataclass(frozen=True)
class DiskMapEnvironment:
    """Everything the check reads from the machine, injectable for tests."""

    volume: DataVolume
    home: str
    run: Run = default_df_runner
    lstat: Lstat = fsread.lstat
    environ: Mapping[str, str] = field(default_factory=dict)
    categories: tuple[CategorySpec, ...] | None = None

    def category_specs(self) -> tuple[CategorySpec, ...]:
        if self.categories is not None:
            return self.categories
        return default_categories(self.home, self.volume.mount)

    def tool_environ(self) -> dict[str, str]:
        return {**self.environ, "HOME": self.home}


def default_environment() -> DiskMapEnvironment:
    """The real data volume and home folder; exit 3 when there is no volume."""
    try:
        info = fsread.lstat(DATA_VOLUME_MOUNT)
    except OSError as error:
        raise ValidationError(
            error=f"the data volume {DATA_VOLUME_MOUNT} was not found",
            reason=f"{DATA_VOLUME_MOUNT}: {error.strerror}",
            suggestion="Run disk map on macOS 10.15 or later with an APFS data volume.",
        ) from error
    volume = DataVolume(DATA_VOLUME_MOUNT, info.st_dev)
    home = os.environ.get("HOME", "")
    return DiskMapEnvironment(volume, home, environ=dict(os.environ))


@dataclass(frozen=True)
class Options:
    top: int = DEFAULT_TOP
    large_file_min_mb: int = DEFAULT_LARGE_FILE_MIN_MB
    skip_categories: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "top": self.top,
            "large_file_min_mb": self.large_file_min_mb,
            "skip_categories": self.skip_categories,
        }


@dataclass(frozen=True)
class Measured:
    """Every walk of one run and the shared identity ledger."""

    placements: tuple[Placement, ...]
    walks: tuple[ScopeWalk, ...]
    ledger: Ledger


def _root_scopes(env: DiskMapEnvironment, given: Sequence[str]) -> list[DeclaredScope]:
    roots = merge_roots(canonical_root(g, env.volume, env.lstat) for g in given)
    return [
        DeclaredScope(ROOT, r.path, r.identity, r.chain, given=r.given) for r in roots
    ]


def _managed(env: DiskMapEnvironment, options: Options) -> tuple[Located, Located]:
    if options.skip_categories:
        return Located(), Located()
    categories = locate_categories(env.category_specs(), env.volume, env.lstat)
    tools = locate_tool_caches(env.tool_environ(), env.run, env.volume, env.lstat)
    return categories, tools


def _unreachable(request: WalkRequest, error: OSError) -> ScopeWalk:
    """A walked scope that vanished or became unreadable after it was located."""
    name = errno.errorcode.get(error.errno) if error.errno else None
    path = request.scope.path
    gap = CoverageEntry(path, coverage_reason(error.errno), name, "lstat")
    return unreached_walk(request, gap)


def _measure(placements: tuple[Placement, ...], large_min: int) -> Measured:
    ledger = Ledger()
    walks: list[ScopeWalk] = []
    for plan in walk_plans(placements):
        request = WalkRequest(plan.scope, plan.inner, plan.excluded)
        try:
            walks.append(walk_scope(request, ledger, large_min))
        except OSError as error:
            walks.append(_unreachable(request, error))
    return Measured(placements, tuple(walks), ledger)


def _views(measured: Measured) -> dict[tuple[str, str], ViewTotals]:
    return {view.key: view for walk in measured.walks for view in walk.views}


def _units(
    measured: Measured, rules: SeeCheckRules, coverage: Sequence[CoverageEntry]
) -> list[Unit]:
    """Reconciliation units in attribution precedence order."""
    views = _views(measured)
    shown = displayed_totals(measured.placements, views, measured.ledger.merged_views())
    counted = {w.path: w.counted_allocated_bytes for w in measured.walks}
    return [
        unit(
            placement,
            shown[(placement.scope.kind, placement.scope.path)],
            counted.get(placement.scope.path, 0),
            rules,
            coverage,
        )
        for placement in measured.placements
    ]


def _extra_sections(
    usage: DfUsage, system: SystemContext, units: Sequence[Unit]
) -> dict[str, Any]:
    """`reconciliation` and `system`; seam: WI-DISK-MAP-TREE adds `tree`."""
    contributions = [Contribution(u.finding.id, u.counted) for u in units]
    return {
        "reconciliation": reconciliation(usage, contributions),
        "system": {"df_data_volume": usage.to_dict(), **dict(system.fields)},
    }


@dataclass(frozen=True)
class Gathered:
    """Measurements plus the sources and gaps found along the way."""

    measured: Measured
    usage: DfUsage
    system: SystemContext
    managed: tuple[Located, Located]

    @property
    def coverage(self) -> tuple[CoverageEntry, ...]:
        found = [c for w in self.measured.walks for c in w.coverage]
        return tuple(found) + tuple(c for m in self.managed for c in m.coverage)

    @property
    def mounts(self) -> tuple[str, ...]:
        found = [m for w in self.measured.walks for m in w.skipped_mounts]
        return tuple(found) + tuple(p for m in self.managed for p in m.mounts)

    def counters(self) -> CostCounters:
        entries = sum(w.entries_visited for w in self.measured.walks)
        counters = CostCounters().add_entries(entries)
        sizes = (self.usage.stdout_bytes, *self.system.stdout_sizes)
        for size in (*sizes, *(s for m in self.managed for s in m.stdout_sizes)):
            counters = counters.add_subprocess_call(size)
        return counters


def _gather(
    env: DiskMapEnvironment, scan_roots: Sequence[str], options: Options
) -> tuple[Gathered, tuple[DeclaredScope, ...]]:
    roots = _root_scopes(env, scan_roots)
    usage = read_df(env.run)
    system = read_system(env.run)
    categories, tools = _managed(env, options)
    scopes = (*roots, *categories.scopes, *tools.scopes)
    placements = plan_scopes(scopes)
    measured = _measure(placements, options.large_file_min_mb * MIB)
    return Gathered(measured, usage, system, (categories, tools)), scopes


def disk_map(
    env: DiskMapEnvironment, scan_roots: Sequence[str], options: Options
) -> CheckResult:
    """Validate roots, read df, measure every scope, then build the result."""
    gathered, scopes = _gather(env, scan_roots, options)
    tool_paths = [s.path for s in scopes if s.kind == "tool_cache"]
    rules = SeeCheckRules.for_home(env.home, env.volume.mount, tool_paths)
    units = _units(gathered.measured, rules, gathered.coverage)
    views = list(_views(gathered.measured).values())
    ledger = gathered.measured.ledger
    merged_inodes = frozenset(k for k in ledger.link_visits if ledger.merged(k))
    depth = {s.path: len(s.chain) for s in scopes if s.kind == ROOT}
    findings = ordered(
        [
            *(u.finding for u in units),
            *first_level(views, ledger.merged_views(), rules, options.top),
            *large_files(views, depth, merged_inodes, rules),
        ]
    )
    extra = _extra_sections(gathered.usage, gathered.system, units)
    roots = [s for s in scopes if s.kind == ROOT]
    summary = {
        "root_count": len(roots),
        "finding_count": len(findings),
        "measured_allocated_bytes": extra["reconciliation"]["measured_allocated_bytes"],
    }
    unavailable = gathered.system.unavailable + gathered.managed[1].unavailable
    return CheckResult(
        data=Data(summary=summary, findings=findings, suggestions=(), extra=extra),
        scope=Scope(
            roots=tuple(ScopeRoot(s.path, s.given, s.identity[0]) for s in roots),
            options=options.to_dict(),
            skipped_mounts=gathered.mounts,
        ),
        counters=gathered.counters(),
        incomplete_coverage=gathered.coverage,
        unavailable_sources=unavailable,
    )
