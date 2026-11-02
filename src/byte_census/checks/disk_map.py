"""`disk map`: where the data volume's used space is, under declared roots.

Steps: canonicalize every `--scan-root` to the data volume (exit 3 otherwise),
read `df -k /System/Volumes/Data` (exit 4 when it fails), walk each
non-nested root once in a single process, then build findings from complete
totals and cut the display to `--top` last. Reconciliation sums the counted
contributions of the reconciliation units in attribution precedence.

Extension seams (later Work Items, not implemented here):
- WI-DISK-MAP-CATEGORIES appends category and tool-cache units after the
  root units in `_reconciliation_units`, claiming through the same `Ledger`,
  and passes tool-cache locations to `SeeCheckRules.for_home`.
- WI-DISK-MAP-TREE adds the `tree` section in `_extra_sections`.
"""

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from byte_census import fsread, runner
from byte_census.checks.disk_map_reconcile import (
    Contribution,
    DfRunner,
    DfUsage,
    parse_df,
    read_df,
    reconciliation,
)
from byte_census.checks.disk_map_roots import (
    DataVolume,
    Lstat,
    RootPlan,
    canonical_root,
    plan_roots,
)
from byte_census.checks.disk_map_see_check import SeeCheckRules
from byte_census.checks.disk_map_walk import (
    FIRST_LEVEL_VIEW,
    LargeFile,
    Ledger,
    RootWalk,
    ViewTotals,
    walk_root,
)
from byte_census.command import CheckResult
from byte_census.cost import CostCounters
from byte_census.errors import ValidationError
from byte_census.model import Data, Finding, Scope, finding_id, order_findings_by_size

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
PREFIX = "map"
KIND_RANK = ("root_total", "first_level", "large_file", "category", "tool_cache")
CAVEAT_CLONES = "apfs_clone_or_shared_extent"
CAVEAT_LINKS = "hard_links_merged"
CAVEAT_SPARSE = "sparse_file"
CAVEAT_INSIDE = "inside_other_scope"
CAVEAT_ORDER = (CAVEAT_CLONES, CAVEAT_LINKS, CAVEAT_SPARSE, CAVEAT_INSIDE)


def default_df_runner(argv: Sequence[str]) -> runner.RunResult:
    return runner.run(argv)


@dataclass(frozen=True)
class DiskMapEnvironment:
    """Everything the check reads from the machine, injectable for tests."""

    volume: DataVolume
    home: str
    run_df: DfRunner = default_df_runner
    lstat: Lstat = fsread.lstat


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
    return DiskMapEnvironment(volume, os.environ.get("HOME", ""))


@dataclass(frozen=True)
class Options:
    top: int = DEFAULT_TOP
    large_file_min_mb: int = DEFAULT_LARGE_FILE_MIN_MB

    def to_dict(self) -> dict[str, int]:
        return {"top": self.top, "large_file_min_mb": self.large_file_min_mb}


@dataclass(frozen=True)
class Measured:
    """Every walk of one run and the run-wide hard-link view."""

    plan: RootPlan
    walks: tuple[RootWalk, ...]
    merged: frozenset[tuple[str, str]] = frozenset()
    merged_inodes: frozenset[tuple[int, int]] = field(default_factory=frozenset)


def _caveats(*codes: str) -> tuple[str, ...]:
    present = set(codes)
    return tuple(code for code in CAVEAT_ORDER if code in present)


@dataclass(frozen=True)
class Shown:
    """What a disk map finding shows besides its kind and target."""

    logical_bytes: int
    allocated_bytes: int
    caveats: tuple[str, ...]
    see_check: str | None
    details: Mapping[str, Any]


def _finding(kind: str, target: str, shown: Shown) -> Finding:
    return Finding(
        id=finding_id(PREFIX, kind, target),
        kind=kind,
        target=target,
        logical_bytes=shown.logical_bytes,
        allocated_bytes=shown.allocated_bytes,
        caveats=shown.caveats,
        see_check=shown.see_check,
        details=shown.details,
    )


def _measure(plan: RootPlan, large_min_bytes: int) -> Measured:
    ledger = Ledger()
    walks = tuple(
        walk_root(root, plan.nested(root), ledger, large_min_bytes)
        for root in plan.walked
    )
    merged_inodes = frozenset(k for k in ledger.link_visits if ledger.merged(k))
    return Measured(plan, walks, ledger.merged_views(), merged_inodes)


def _views(measured: Measured, kind: str) -> dict[str, ViewTotals]:
    return {
        view.path: view
        for walk in measured.walks
        for view in walk.views
        if view.kind == kind
    }


def _root_units(measured: Measured, rules: SeeCheckRules) -> list[tuple[Finding, int]]:
    """One root_total finding and counted contribution per root, by path."""
    views = _views(measured, "root_total")
    counted = {walk.root: walk.counted_allocated_bytes for walk in measured.walks}
    units: list[tuple[Finding, int]] = []
    for root in measured.plan.roots:
        view = views[root.path]
        nested = measured.plan.is_nested(root.path)
        merged = view.key in measured.merged
        caveats = [CAVEAT_CLONES]
        caveats += [CAVEAT_LINKS] if merged else []
        caveats += [CAVEAT_INSIDE] if nested else []
        own = 0 if nested else counted[root.path]
        details = {
            "given": root.given,
            "counted_allocated_bytes": own,
            "overlap": "inside_scan_root" if nested else None,
        }
        shown = Shown(
            view.logical_bytes,
            view.allocated_bytes,
            _caveats(*caveats),
            rules.see_check(root.path, "root_total"),
            details,
        )
        finding = _finding("root_total", root.path, shown)
        units.append((finding, own))
    return units


def _first_level(
    measured: Measured, rules: SeeCheckRules, top: int
) -> tuple[Finding, ...]:
    """The `top` largest first-level folders of each root."""
    by_owner: dict[str, list[Finding]] = {}
    for view in _views(measured, FIRST_LEVEL_VIEW).values():
        merged = view.key in measured.merged
        shown = Shown(
            view.logical_bytes,
            view.allocated_bytes,
            _caveats(CAVEAT_LINKS) if merged else (),
            rules.see_check(view.path, FIRST_LEVEL_VIEW),
            {"root": view.owner},
        )
        finding = _finding(FIRST_LEVEL_VIEW, view.path, shown)
        by_owner.setdefault(view.owner, []).append(finding)
    return tuple(
        finding
        for owner in sorted(by_owner)
        for finding in order_findings_by_size(by_owner[owner])[:top]
    )


def _large_file(item: LargeFile, measured: Measured, rules: SeeCheckRules) -> Finding:
    codes = [CAVEAT_LINKS] if item.inode in measured.merged_inodes else []
    codes += [CAVEAT_SPARSE] if item.logical_bytes > item.allocated_bytes else []
    shown = Shown(
        item.logical_bytes,
        item.allocated_bytes,
        _caveats(*codes),
        rules.see_check(item.path, "large_file"),
        {"root": item.root},
    )
    return _finding("large_file", item.path, shown)


def _ordered(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    """Kind rank, then the kind's size key descending, then target."""
    ordered: list[Finding] = []
    for kind in KIND_RANK:
        group = [f for f in findings if f.kind == kind]
        key = "logical_bytes" if kind == "large_file" else "allocated_bytes"
        ordered.extend(order_findings_by_size(group, key))
    return tuple(ordered)


def _reconciliation_units(
    measured: Measured, rules: SeeCheckRules
) -> list[tuple[Finding, int]]:
    """Reconciliation units in attribution precedence: roots by path.

    Seam: categories (catalog order) and tool caches (uv, npm, brew) follow.
    """
    return _root_units(measured, rules)


def _extra_sections(
    usage: DfUsage, units: Sequence[tuple[Finding, int]]
) -> dict[str, Any]:
    """`reconciliation` and `system`; seam: WI-DISK-MAP-TREE adds `tree`."""
    contributions = [Contribution(f.id, counted) for f, counted in units]
    return {
        "reconciliation": reconciliation(usage, contributions),
        "system": {"df_data_volume": usage.to_dict()},
    }


def _counters(measured: Measured, usage: DfUsage) -> CostCounters:
    entries = sum(walk.entries_visited for walk in measured.walks)
    return CostCounters().add_entries(entries).add_subprocess_call(usage.stdout_bytes)


def disk_map(
    env: DiskMapEnvironment, scan_roots: Sequence[str], options: Options
) -> CheckResult:
    """Validate roots, read df, measure every root, then build the result."""
    roots = [canonical_root(given, env.volume, env.lstat) for given in scan_roots]
    plan = plan_roots(roots)
    usage = read_df(env.run_df)
    measured = _measure(plan, options.large_file_min_mb * MIB)
    rules = SeeCheckRules.for_home(env.home, env.volume.mount)
    units = _reconciliation_units(measured, rules)
    large = [
        _large_file(item, measured, rules)
        for walk in measured.walks
        for item in walk.large_files
    ]
    findings = _ordered(
        [f for f, _ in units] + [*_first_level(measured, rules, options.top), *large]
    )
    extra = _extra_sections(usage, units)
    summary = {
        "root_count": len(plan.roots),
        "finding_count": len(findings),
        "measured_allocated_bytes": extra["reconciliation"]["measured_allocated_bytes"],
    }
    return CheckResult(
        data=Data(summary=summary, findings=findings, suggestions=(), extra=extra),
        scope=Scope(
            roots=plan.roots,
            options=options.to_dict(),
            skipped_mounts=tuple(m for w in measured.walks for m in w.skipped_mounts),
        ),
        counters=_counters(measured, usage),
        incomplete_coverage=tuple(c for w in measured.walks for c in w.coverage),
    )
