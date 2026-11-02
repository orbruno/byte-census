"""Attribution planning for `disk map` (quantities.md, attribution precedence).

Declared scopes arrive in precedence order: roots by path, categories in
catalog order, tool caches uv, npm, brew. Containment is decided by identity
(an earlier scope's directory is the scope or one of its ancestors).

- A scope inside an earlier root is shown, not walked: `equals_scan_root` or
  `inside_scan_root` (a nested root is always `inside_scan_root`).
- A scope inside an earlier category or tool cache: `inside_category`.
- Otherwise it is walked, pruning earlier walked scopes inside it; when one
  of those is a root its overlap is `encloses_scan_root`.

A scope that is not walked is a view in the innermost walked scope that
contains it. Displayed totals of a scope are its own view united with the
displayed totals of every pruned scope inside it, hard links merged.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from byte_census.checks.disk_map_walk import InodeKey, LinkBytes, ViewSpec, ViewTotals

ROOT = "root_total"
CATEGORY = "category"
TOOL_CACHE = "tool_cache"


@dataclass(frozen=True)
class DeclaredScope:
    """A root, category, or tool cache with its identity and ancestor chain."""

    kind: str
    path: str
    identity: InodeKey
    chain: tuple[InodeKey, ...]
    given: str = ""
    label: str = ""
    tool: str = ""

    def contains(self, other: "DeclaredScope") -> bool:
        return self.identity == other.identity or self.identity in other.chain

    def spec(self) -> ViewSpec:
        is_root = self.kind == ROOT
        return ViewSpec(self.kind, self.path, self.identity, is_root, is_root)


@dataclass(frozen=True)
class Placement:
    """Where a scope is measured and how it overlaps earlier scopes."""

    scope: DeclaredScope
    walked: bool
    overlap: str | None
    host: str
    excluded: tuple[str, ...] = ()


def _overlap_inside(scope: DeclaredScope, earlier: Sequence[Placement]) -> str | None:
    holders = [p.scope for p in earlier if p.scope.contains(scope)]
    roots = [h for h in holders if h.kind == ROOT]
    if roots:
        same = any(h.identity == scope.identity for h in roots)
        return "equals_scan_root" if same and scope.kind != ROOT else "inside_scan_root"
    return "inside_category" if holders else None


def _host(scope: DeclaredScope, earlier: Sequence[Placement]) -> str:
    walked = [p.scope for p in earlier if p.walked and p.scope.contains(scope)]
    return max(walked, key=lambda s: len(s.chain)).path


def _maximal(inner: Sequence[DeclaredScope]) -> tuple[DeclaredScope, ...]:
    return tuple(
        s for s in inner if not any(o is not s and o.contains(s) for o in inner)
    )


def _place(scope: DeclaredScope, earlier: Sequence[Placement]) -> Placement:
    overlap = _overlap_inside(scope, earlier)
    if overlap is not None:
        return Placement(scope, False, overlap, _host(scope, earlier))
    inner = [p.scope for p in earlier if p.walked and scope.contains(p.scope)]
    encloses = any(p.scope.kind == ROOT and scope.contains(p.scope) for p in earlier)
    return Placement(
        scope,
        True,
        "encloses_scan_root" if encloses else None,
        scope.path,
        tuple(s.path for s in _maximal(inner)),
    )


def plan_scopes(scopes: Iterable[DeclaredScope]) -> tuple[Placement, ...]:
    """Place every scope, in the precedence order given."""
    placements: list[Placement] = []
    for scope in scopes:
        placements.append(_place(scope, placements))
    return tuple(placements)


@dataclass(frozen=True)
class WalkPlan:
    """What one walked scope shows inside itself and which subtrees it prunes."""

    scope: ViewSpec
    inner: tuple[ViewSpec, ...]
    excluded: frozenset[InodeKey]


def walk_plans(placements: Sequence[Placement]) -> tuple[WalkPlan, ...]:
    """One plan per walked scope, in precedence order."""
    by_path = {p.scope.path: p.scope for p in placements if p.walked}
    return tuple(
        WalkPlan(
            scope=p.scope.spec(),
            inner=tuple(
                q.scope.spec()
                for q in placements
                if not q.walked and q.host == p.scope.path
            ),
            excluded=frozenset(by_path[x].identity for x in p.excluded),
        )
        for p in placements
        if p.walked
    )


@dataclass(frozen=True)
class Displayed:
    """Displayed totals of a scope; null bytes when it was never reached."""

    logical_bytes: int | None
    allocated_bytes: int | None
    sparse: bool
    merged: bool
    observed: bool
    links: tuple[LinkBytes, ...] = ()


def from_view(view: ViewTotals, merged: bool) -> Displayed:
    if not view.observed:
        return Displayed(None, None, False, False, False)
    return Displayed(
        view.logical_bytes, view.allocated_bytes, view.sparse, merged, True, view.links
    )


def union(parts: Sequence[Displayed]) -> Displayed:
    """Distinct-inode union: bytes outside hard links add up, links count once."""
    seen = [p for p in parts if p.observed]
    if not seen or not parts[0].observed:
        return parts[0]
    links: dict[InodeKey, tuple[int, int]] = {}
    allocated = logical = 0
    for part in seen:
        allocated += (part.allocated_bytes or 0) - sum(a for _, a, _ in part.links)
        logical += (part.logical_bytes or 0) - sum(lg for _, _, lg in part.links)
        links.update({key: (a, lg) for key, a, lg in part.links})
    shared = sum(len(p.links) for p in seen) > len(links)
    return Displayed(
        logical + sum(lg for _, lg in links.values()),
        allocated + sum(a for a, _ in links.values()),
        any(p.sparse for p in seen),
        shared or any(p.merged for p in seen),
        True,
        tuple((k, a, lg) for k, (a, lg) in sorted(links.items())),
    )


def displayed_totals(
    placements: Sequence[Placement],
    views: Mapping[tuple[str, str], ViewTotals],
    merged: frozenset[tuple[str, str]],
) -> dict[tuple[str, str], Displayed]:
    """Displayed totals per (kind, path), unions resolved in precedence order."""
    walked = {p.scope.path: p for p in placements if p.walked}
    result: dict[tuple[str, str], Displayed] = {}
    for placement in placements:
        scope = placement.scope
        key = (scope.kind, scope.path)
        own = from_view(views[key], key in merged)
        pruned = walked[placement.host].excluded
        inner = [
            result[(walked[x].scope.kind, x)]
            for x in pruned
            if scope.contains(walked[x].scope)
        ]
        result[key] = union([own, *inner])
    return result
