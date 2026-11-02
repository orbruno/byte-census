"""Tests for the disk map folder tree (WI-DISK-MAP-TREE AC-01).

The tree is `data.tree`: `depth`, `min_bytes`, and one node per declared
root (`path` ascending), each with `children` folders down to `--tree-depth`
levels whose displayed allocated bytes reach `--tree-min-mb` MiB. Children
are ordered by allocated bytes descending, then path. Expected sizes come
from `lstat`.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from byte_census import fsread
from byte_census.cli import main
from tests.support.disk_map_world import (
    MIB,
    OtherDevice,
    World,
    expected_allocated,
    make_file,
    new_world,
    run_map,
)
from tests.support.snapshots import assert_json_snapshot


@pytest.fixture
def world(tmp_path: Path) -> World:
    return new_world(tmp_path)


def build(world: World) -> Path:
    root = world.home / "Projects"
    make_file(root / "big" / "a" / "b" / "c" / "d" / "deep.bin", 300_000)
    make_file(root / "big" / "a" / "side.bin", 100_000)
    make_file(root / "mid" / "m.bin", 150_000)
    make_file(root / "small" / "s.bin", 5_000)
    make_file(root / "loose.bin", 7_000)
    (root / "empty").mkdir()
    return root


def tree_of(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["data"]["tree"]


def nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    found = [node]
    for child in node["children"]:
        found.extend(nodes(child))
    return found


def relative_paths(node: dict[str, Any], root: Path) -> set[str]:
    return {os.path.relpath(n["path"], root) for n in nodes(node)}


def test_tree_lists_every_folder_down_to_the_depth(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    _, payload = run_map(monkeypatch, world, [root], "--tree-min-mb", "0")

    tree = tree_of(payload)
    assert (tree["depth"], tree["min_bytes"]) == (4, 0)
    [top] = tree["roots"]
    assert top["path"] == str(root)
    assert relative_paths(top, root) == {
        ".",
        "big",
        "big/a",
        "big/a/b",
        "big/a/b/c",
        "mid",
        "small",
        "empty",
    }
    for node in nodes(top):
        assert node["allocated_bytes"] == expected_allocated(Path(node["path"]))


def test_children_are_ordered_by_size_then_path(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    _, payload = run_map(monkeypatch, world, [root], "--tree-min-mb", "0")

    for node in nodes(tree_of(payload)["roots"][0]):
        keys = [(-c["allocated_bytes"], c["path"]) for c in node["children"]]
        assert keys == sorted(keys)
    names = [Path(c["path"]).name for c in tree_of(payload)["roots"][0]["children"]]
    assert names == ["big", "mid", "small", "empty"]


def test_minimum_size_prunes_small_folders(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    make_file(root / "huge" / "h.bin", 2 * MIB)
    _, payload = run_map(monkeypatch, world, [root], "--tree-min-mb", "1")

    [top] = tree_of(payload)["roots"]
    assert tree_of(payload)["min_bytes"] == MIB
    assert relative_paths(top, root) == {".", "huge"}
    assert top["allocated_bytes"] == expected_allocated(root)


def test_defaults_are_depth_4_and_100_mib(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    _, payload = run_map(monkeypatch, world, [root])

    tree = tree_of(payload)
    assert (tree["depth"], tree["min_bytes"]) == (4, 100 * MIB)
    assert tree["roots"][0]["children"] == []
    options = payload["meta"]["scope"]["options"]
    assert (options["tree_depth"], options["tree_min_mb"]) == (4, 100)


def test_depth_zero_keeps_only_the_roots(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    _, payload = run_map(
        monkeypatch, world, [root], "--tree-depth", "0", "--tree-min-mb", "0"
    )

    assert tree_of(payload)["roots"] == [
        {"path": str(root), "allocated_bytes": expected_allocated(root), "children": []}
    ]


def test_every_root_has_a_tree_including_nested_roots(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    other = world.home / "Other"
    make_file(other / "x" / "x.bin", 1000)
    inner = root / "big" / "a"
    _, payload = run_map(monkeypatch, world, [other, inner, root], "--tree-min-mb", "0")

    roots = tree_of(payload)["roots"]
    assert [r["path"] for r in roots] == sorted([str(other), str(inner), str(root)])
    nested = next(r for r in roots if r["path"] == str(inner))
    assert relative_paths(nested, inner) == {".", "b", "b/c", "b/c/d"}
    assert nested["allocated_bytes"] == expected_allocated(inner)


def test_tree_is_built_from_the_single_walk(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    listed: list[str] = []
    real = fsread.list_directory

    def counting(path: Any, root_dev: int | None = None) -> Any:
        listed.append(os.fspath(path))
        return real(path, root_dev)

    monkeypatch.setattr(fsread, "list_directory", counting)
    run_map(monkeypatch, world, [root], "--tree-min-mb", "0", "--skip-categories")

    walked = [p for p in listed if p.startswith(str(root))]
    assert len(walked) == len(set(walked))


def test_mounts_are_not_tree_nodes(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = build(world)
    mounted = root / "mid"
    real = fsread.lstat

    def fake(path: Any) -> Any:
        info = real(path)
        return OtherDevice(info) if os.fspath(path) == str(mounted) else info

    monkeypatch.setattr(fsread, "lstat", fake)
    _, payload = run_map(monkeypatch, world, [root], "--tree-min-mb", "0")

    assert "mid" not in relative_paths(tree_of(payload)["roots"][0], root)


def test_unobserved_nested_root_has_a_null_node(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    outer = world.home / "outer"
    locked = outer / "locked"
    inner = locked / "inner"
    make_file(inner / "f.bin", 1000)
    locked.chmod(0o311)
    try:
        _, payload = run_map(monkeypatch, world, [outer, inner], "--tree-min-mb", "0")
    finally:
        locked.chmod(0o755)

    node = next(r for r in tree_of(payload)["roots"] if r["path"] == str(inner))
    assert node == {"path": str(inner), "allocated_bytes": None, "children": []}


@pytest.mark.parametrize(
    "args", [["--tree-depth", "-1"], ["--tree-min-mb", "-1"], ["--tree-depth", "x"]]
)
def test_invalid_tree_options_are_usage_errors(args: list[str], world: World) -> None:
    result = CliRunner().invoke(
        main, ["disk", "map", "--scan-root", str(world.home), *args]
    )

    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "usage_error"


def test_tree_snapshot(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    root = build(world)
    result, payload = run_map(
        monkeypatch, world, [root], "--tree-min-mb", "0", "--skip-categories"
    )

    assert result.exit_code == 0, result.stderr
    assert list(payload["data"]) == [
        "summary",
        "findings",
        "reconciliation",
        "system",
        "tree",
        "suggestions",
    ]
    assert_json_snapshot(payload["data"]["tree"], "disk-map-tree", roots=[world.data])
