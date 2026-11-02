"""The `data.tree` section of `disk map` (parity matrix P14).

One node per declared root, in ascending path order, with the folders below
it down to `--tree-depth` levels whose displayed allocated bytes reach
`--tree-min-mb` MiB. The folder totals come from the same single walk as
every other figure (`ScopeWalk.tree_nodes`); nothing is walked again. A
folder smaller than the minimum is dropped with everything below it, which
loses nothing: a folder's displayed total includes all of its subfolders.
A root that its walk never reached has a null size and no children.
Children are ordered by allocated bytes descending, then path.
"""

import os
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from byte_census.checks.disk_map_walk import ViewTotals

Node = dict[str, Any]


def _children_by_parent(
    root: str, nodes: Iterable[ViewTotals], min_bytes: int
) -> dict[str, list[ViewTotals]]:
    kept = [n for n in nodes if n.owner == root and n.allocated_bytes >= min_bytes]
    by_parent: dict[str, list[ViewTotals]] = {}
    for node in kept:
        by_parent.setdefault(os.path.dirname(node.path), []).append(node)
    return by_parent


def _node(
    path: str, allocated: int | None, by_parent: Mapping[str, list[ViewTotals]]
) -> Node:
    children = sorted(
        by_parent.get(path, []), key=lambda n: (-n.allocated_bytes, n.path)
    )
    return {
        "path": path,
        "allocated_bytes": allocated,
        "children": [_node(c.path, c.allocated_bytes, by_parent) for c in children],
    }


def build_tree(
    roots: Sequence[tuple[str, int | None]],
    nodes: Sequence[ViewTotals],
    depth: int,
    min_bytes: int,
) -> dict[str, Any]:
    """The tree section; `roots` pairs each root path with its displayed size."""
    trees = []
    for path, allocated in sorted(roots):
        by_parent = (
            {} if allocated is None else _children_by_parent(path, nodes, min_bytes)
        )
        trees.append(_node(path, allocated, by_parent))
    return {"depth": depth, "min_bytes": min_bytes, "roots": trees}
