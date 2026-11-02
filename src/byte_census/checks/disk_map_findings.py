"""Findings for `disk map`: reconciliation units, first-level folders, large files.

Reconciliation units are roots, categories, and tool caches, one per
placement, with `counted_allocated_bytes` and `overlap` in `details`. A
scope that its host walk never reached (an ancestor could not be listed) is
`unobserved`: its bytes are null, not zero, and `coverage_path` names the
coverage entry that hid it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from byte_census.checks.disk_map_roots import is_inside
from byte_census.checks.disk_map_scopes import (
    CATEGORY,
    ROOT,
    TOOL_CACHE,
    Displayed,
    Placement,
)
from byte_census.checks.disk_map_see_check import SeeCheckRules
from byte_census.checks.disk_map_walk import (
    FIRST_LEVEL_VIEW,
    LargeFile,
    ViewTotals,
    select_large,
)
from byte_census.model import (
    Classification,
    CoverageEntry,
    Finding,
    finding_id,
    order_findings_by_size,
)

PREFIX = "map"
KIND_RANK = (ROOT, FIRST_LEVEL_VIEW, "large_file", CATEGORY, TOOL_CACHE)
CAVEAT_CLONES = "apfs_clone_or_shared_extent"
CAVEAT_LINKS = "hard_links_merged"
CAVEAT_SPARSE = "sparse_file"
CAVEAT_INSIDE = "inside_other_scope"
CAVEAT_ORDER = (CAVEAT_CLONES, CAVEAT_LINKS, CAVEAT_SPARSE, CAVEAT_INSIDE)


def caveats(*codes: str) -> tuple[str, ...]:
    present = set(codes)
    return tuple(code for code in CAVEAT_ORDER if code in present)


def _content_caveats(shown: Displayed) -> list[str]:
    return [CAVEAT_LINKS] * shown.merged + [CAVEAT_SPARSE] * shown.sparse


@dataclass(frozen=True)
class Unit:
    """A reconciliation unit: its finding and counted contribution."""

    finding: Finding
    counted: int


def _identity_details(placement: Placement) -> dict[str, Any]:
    scope = placement.scope
    if scope.kind == ROOT:
        return {"given": scope.given}
    if scope.kind == CATEGORY:
        return {"label": scope.label}
    return {"tool": scope.tool}


def _hidden_by(path: str, coverage: Sequence[CoverageEntry]) -> str | None:
    holders = [entry.path for entry in coverage if is_inside(path, entry.path)]
    return max(holders, key=len) if holders else None


def unit(
    placement: Placement,
    shown: Displayed,
    counted: int,
    rules: SeeCheckRules,
    coverage: Sequence[CoverageEntry],
) -> Unit:
    """The finding for one root, category, or tool cache."""
    scope = placement.scope
    own = counted if placement.walked else 0
    codes = [CAVEAT_CLONES] if scope.kind == ROOT else []
    codes += _content_caveats(shown)
    codes += [] if placement.walked else [CAVEAT_INSIDE]
    details = {
        **_identity_details(placement),
        "counted_allocated_bytes": own,
        "overlap": placement.overlap,
    }
    if not shown.observed:
        details |= {
            "unobserved": True,
            "coverage_path": _hidden_by(scope.path, coverage),
        }
    finding = Finding(
        id=finding_id(PREFIX, scope.kind, scope.path),
        kind=scope.kind,
        target=scope.path,
        logical_bytes=shown.logical_bytes,
        allocated_bytes=shown.allocated_bytes,
        caveats=caveats(*codes),
        see_check=rules.see_check(scope.path, scope.kind),
        classification=Classification(owner=scope.tool),
        details=details,
    )
    return Unit(finding, own)


def first_level(
    views: Sequence[ViewTotals],
    merged: frozenset[tuple[str, str]],
    rules: SeeCheckRules,
    top: int,
) -> tuple[Finding, ...]:
    """The `top` largest first-level folders of each root."""
    by_owner: dict[str, list[Finding]] = {}
    for view in views:
        if view.kind != FIRST_LEVEL_VIEW:
            continue
        codes = [CAVEAT_LINKS] * (view.key in merged) + [CAVEAT_SPARSE] * view.sparse
        finding = Finding(
            id=finding_id(PREFIX, FIRST_LEVEL_VIEW, view.path),
            kind=FIRST_LEVEL_VIEW,
            target=view.path,
            logical_bytes=view.logical_bytes,
            allocated_bytes=view.allocated_bytes,
            caveats=caveats(*codes),
            see_check=rules.see_check(view.path, FIRST_LEVEL_VIEW),
            details={"root": view.owner},
        )
        by_owner.setdefault(view.owner, []).append(finding)
    return tuple(
        finding
        for owner in sorted(by_owner)
        for finding in order_findings_by_size(by_owner[owner])[:top]
    )


def large_files(
    views: Sequence[ViewTotals],
    depth: Mapping[str, int],
    merged_inodes: frozenset[tuple[int, int]],
    rules: SeeCheckRules,
) -> tuple[Finding, ...]:
    """Each root's 20 largest files; a file several roots select is listed
    once, under the innermost of them."""
    owned: dict[str, LargeFile] = {}
    for view in views:
        if view.kind != ROOT:
            continue
        for item in select_large(view.large_files):
            current = owned.get(item.path)
            if current is None or depth[item.root] > depth[current.root]:
                owned[item.path] = item
    return tuple(_large(item, merged_inodes, rules) for item in owned.values())


def _large(
    item: LargeFile, merged_inodes: frozenset[tuple[int, int]], rules: SeeCheckRules
) -> Finding:
    codes = [CAVEAT_LINKS] * (item.inode in merged_inodes)
    codes += [CAVEAT_SPARSE] * (item.logical_bytes > item.allocated_bytes)
    return Finding(
        id=finding_id(PREFIX, "large_file", item.path),
        kind="large_file",
        target=item.path,
        logical_bytes=item.logical_bytes,
        allocated_bytes=item.allocated_bytes,
        caveats=caveats(*codes),
        see_check=rules.see_check(item.path, "large_file"),
        details={"root": item.root},
    )


def ordered(findings: Sequence[Finding]) -> tuple[Finding, ...]:
    """Kind rank, then the kind's size key descending, then target."""
    result: list[Finding] = []
    for kind in KIND_RANK:
        group = [f for f in findings if f.kind == kind]
        key = "logical_bytes" if kind == "large_file" else "allocated_bytes"
        result.extend(order_findings_by_size(group, key))
    return tuple(result)
