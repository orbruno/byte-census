"""Tests for disk map categories and tool caches (WI-DISK-MAP-CATEGORIES).

The fixture mirrors docs/contracts/examples/disk-map.json: roots
Application Support and Developer/Xcode; categories equal to, inside, and
enclosing a root; uv outside every scope and brew inside User caches.
Expected numbers come from `lstat` through tests.support.disk_map_world.
"""

import errno
import os
from pathlib import Path
from typing import Any

import pytest

from byte_census import fsread
from byte_census.checks.disk_map_categories import CategorySpec, default_categories
from tests.support.disk_map_world import (
    BREW_ARGV,
    DOCKER_ARGV,
    DOCKER_TEXT,
    UV_ARGV,
    OtherDevice,
    World,
    expected_allocated,
    expected_logical,
    findings_of,
    make_file,
    new_world,
    run_map,
)
from tests.support.snapshots import assert_json_snapshot


@pytest.fixture
def world(tmp_path: Path) -> World:
    return new_world(tmp_path)


class Tree:
    """Paths of the example-shaped fixture."""

    def __init__(self, world: World) -> None:
        library = world.home / "Library"
        self.library = library
        self.support = library / "Application Support"
        self.backup = self.support / "MobileSync" / "Backup"
        self.developer = library / "Developer"
        self.xcode = self.developer / "Xcode"
        self.caches = library / "Caches"
        self.brew = self.caches / "Homebrew"
        self.containers = library / "Containers"
        self.groups = library / "Group Containers"
        self.mail = library / "Mail"
        self.messages = library / "Messages"
        self.downloads = world.home / "Downloads"
        self.applications = world.data / "Applications"
        self.uv = world.home / ".cache" / "uv"

    def roots(self) -> list[Path]:
        return [self.support, self.xcode]

    def categories(self) -> list[Path]:
        return [
            self.caches, self.support, self.containers, self.groups,
            self.developer, self.backup, self.mail, self.messages,
            self.downloads, self.applications,
        ]  # fmt: skip


def build(world: World) -> Tree:
    tree = Tree(world)
    make_file(tree.support / "Steam" / "game.pak", 400_000)
    make_file(tree.backup / "0000" / "Manifest.db", 120_000)
    make_file(tree.support / "Google" / "chrome.bin", 30_000)
    make_file(tree.xcode / "DerivedData" / "build.o", 200_000)
    make_file(tree.xcode / "iOS DeviceSupport" / "sym.bin", 90_000)
    make_file(tree.developer / "CoreSimulator" / "device.img", 70_000)
    make_file(tree.caches / "app" / "c.bin", 60_000)
    make_file(tree.brew / "bottle.tar", 50_000)
    make_file(tree.containers / "com.example" / "data.bin", 80_000)
    make_file(tree.groups / "group.example" / "g.bin", 40_000)
    make_file(tree.mail / "V10" / "mail.emlx", 10_000)
    make_file(tree.messages / "chat.db", 10_000)
    make_file(tree.downloads / "setup.dmg", 25_000)
    make_file(tree.applications / "Example.app" / "binary", 35_000)
    make_file(tree.uv / "wheels" / "w.whl", 45_000)
    world.runner.answers[UV_ARGV] = str(tree.uv) + "\n"
    world.runner.answers[BREW_ARGV] = str(tree.brew) + "\n"
    world.runner.answers[DOCKER_ARGV] = DOCKER_TEXT
    return tree


def unit(payload: dict[str, Any], kind: str, path: Path) -> dict[str, Any]:
    return findings_of(payload, kind)[str(path)]


def counted(payload: dict[str, Any], kind: str, path: Path) -> int:
    return unit(payload, kind, path)["details"]["counted_allocated_bytes"]


def test_snapshot(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    tree = build(world)
    result, payload = run_map(monkeypatch, world, tree.roots(), "--large-file-min", "0")

    assert result.exit_code == 0, result.stderr
    # Fake tool output embeds the fixture path, whose length differs between
    # machines, so the counter is checked exactly here and masked below.
    cost = payload["meta"]["cost"]
    assert cost["subprocess_stdout_bytes"] == world.runner.stdout_bytes_returned
    assert_json_snapshot(
        payload,
        "disk-map-categories",
        roots=[world.data],
        volatile=["meta.cost.subprocess_stdout_bytes"],
    )


def test_enclosing_category_contributes_only_its_remainder(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    _, payload = run_map(monkeypatch, world, tree.roots())

    developer = unit(payload, "category", tree.developer)
    assert developer["details"]["label"] == "Developer data"
    assert developer["details"]["overlap"] == "encloses_scan_root"
    assert developer["allocated_bytes"] == expected_allocated(tree.developer)
    assert developer["logical_bytes"] == expected_logical(tree.developer)
    assert developer["details"]["counted_allocated_bytes"] == (
        expected_allocated(tree.developer) - expected_allocated(tree.xcode)
    )
    assert "inside_other_scope" not in developer["caveats"]


def test_shared_hard_link_is_merged_in_the_enclosing_category(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    linked = tree.xcode / "DerivedData" / "build.o"
    os.link(linked, tree.developer / "CoreSimulator" / "build-link.o")
    _, payload = run_map(monkeypatch, world, tree.roots())

    developer = unit(payload, "category", tree.developer)
    assert developer["allocated_bytes"] == expected_allocated(tree.developer)
    assert developer["details"]["counted_allocated_bytes"] == (
        expected_allocated(tree.developer) - expected_allocated(tree.xcode)
    )
    assert "hard_links_merged" in developer["caveats"]


def test_categories_inside_or_equal_to_a_root_count_zero(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    _, payload = run_map(monkeypatch, world, tree.roots())

    support = unit(payload, "category", tree.support)
    root = unit(payload, "root_total", tree.support)
    assert support["details"] == {
        "label": "Application support",
        "counted_allocated_bytes": 0,
        "overlap": "equals_scan_root",
    }
    assert support["caveats"] == ["inside_other_scope"]
    assert support["allocated_bytes"] == root["allocated_bytes"]
    backup = unit(payload, "category", tree.backup)
    assert backup["details"]["overlap"] == "inside_scan_root"
    assert backup["details"]["counted_allocated_bytes"] == 0
    assert backup["details"]["label"] == "Device backups (inside Application support)"
    assert backup["allocated_bytes"] == expected_allocated(tree.backup)


def test_disjoint_categories_and_tool_caches_count_once(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    _, payload = run_map(monkeypatch, world, tree.roots())

    for path in (tree.caches, tree.containers, tree.downloads, tree.applications):
        assert counted(payload, "category", path) == expected_allocated(path)
    uv = unit(payload, "tool_cache", tree.uv)
    assert uv["details"] == {
        "tool": "uv",
        "counted_allocated_bytes": expected_allocated(tree.uv),
        "overlap": None,
    }
    assert uv["classification"]["owner"] == "uv"
    assert uv["see_check"] == "caches scan"
    brew = unit(payload, "tool_cache", tree.brew)
    assert brew["details"]["overlap"] == "inside_category"
    assert brew["details"]["counted_allocated_bytes"] == 0
    assert brew["caveats"] == ["inside_other_scope"]
    assert brew["allocated_bytes"] == expected_allocated(tree.brew)
    assert unit(payload, "category", tree.caches)["see_check"] == "caches scan"
    assert unit(payload, "category", tree.downloads)["see_check"] == ("duplicates scan")


def test_measured_is_the_union_of_every_scope(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    expected = expected_allocated(*tree.roots(), *tree.categories(), tree.uv)
    _, payload = run_map(monkeypatch, world, tree.roots())

    reconciliation = payload["data"]["reconciliation"]
    assert reconciliation["measured_allocated_bytes"] == expected
    assert payload["data"]["summary"]["measured_allocated_bytes"] == expected
    assert (
        sum(c["counted_allocated_bytes"] for c in reconciliation["contributions"])
        == expected
    )


def test_contributions_follow_attribution_precedence(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    _, payload = run_map(monkeypatch, world, tree.roots())

    ids = {(f["kind"], f["target"]): f["id"] for f in payload["data"]["findings"]}
    order = [
        ("root_total", tree.support),
        ("root_total", tree.xcode),
        *(("category", path) for path in tree.categories()),
        ("tool_cache", tree.uv),
        ("tool_cache", tree.brew),
    ]
    contributions = payload["data"]["reconciliation"]["contributions"]
    assert [c["finding_id"] for c in contributions] == [
        ids[(kind, str(path))] for kind, path in order
    ]


def test_skip_categories_measures_only_the_roots(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    _, payload = run_map(monkeypatch, world, tree.roots(), "--skip-categories")

    kinds = {f["kind"] for f in payload["data"]["findings"]}
    assert kinds == {"root_total", "first_level"}
    assert payload["meta"]["scope"]["options"]["skip_categories"] is True
    assert UV_ARGV not in world.runner.calls
    assert BREW_ARGV not in world.runner.calls
    assert payload["data"]["summary"]["measured_allocated_bytes"] == (
        expected_allocated(*tree.roots())
    )


def test_missing_categories_are_omitted(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = world.home / "Documents"
    make_file(root / "f.bin", 1000)
    _, payload = run_map(monkeypatch, world, [root])

    assert findings_of(payload, "category") == {}
    assert payload["meta"]["status"] == "complete"


def test_denials_inside_categories_are_coverage_gaps(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    real = fsread._sorted_entries

    def listing(path: str) -> Any:
        if path == str(tree.messages):
            raise PermissionError(errno.EPERM, "Operation not permitted", path)
        return real(path)

    monkeypatch.setattr(fsread, "_sorted_entries", listing)
    tree.mail.chmod(0)
    try:
        _, payload = run_map(monkeypatch, world, tree.roots())
    finally:
        tree.mail.chmod(0o755)

    gaps = {e["path"]: e for e in payload["meta"]["incomplete_coverage"]}
    assert gaps[str(tree.mail)]["reason"] == "permission_denied"
    assert gaps[str(tree.messages)] == {
        "path": str(tree.messages),
        "reason": "privacy_denied",
        "errno": "EPERM",
        "operation": "scandir",
    }
    assert payload["meta"]["status"] == "partial"
    mail = unit(payload, "category", tree.mail)
    assert mail["allocated_bytes"] == os.lstat(tree.mail).st_blocks * 512


def test_category_that_cannot_be_examined_is_a_coverage_gap(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    real = os.lstat

    def lstat(path: Any) -> Any:
        if os.fspath(path) == str(tree.groups):
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return real(path)

    world.lstat = lstat
    _, payload = run_map(monkeypatch, world, tree.roots())

    assert str(tree.groups) not in findings_of(payload, "category")
    assert {
        "path": str(tree.groups),
        "reason": "permission_denied",
        "errno": "EACCES",
        "operation": "lstat",
    } in payload["meta"]["incomplete_coverage"]


def test_category_on_another_device_is_a_skipped_mount(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    real = os.lstat

    def lstat(path: Any) -> Any:
        info = real(path)
        return OtherDevice(info) if os.fspath(path) == str(tree.applications) else info

    world.lstat = lstat
    _, payload = run_map(monkeypatch, world, tree.roots())

    assert str(tree.applications) not in findings_of(payload, "category")
    assert str(tree.applications) in payload["meta"]["scope"]["skipped_mounts"]


def test_two_tools_at_one_location_are_one_tool_cache(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    world.runner.answers[BREW_ARGV] = str(tree.uv) + "\n"
    _, payload = run_map(monkeypatch, world, tree.roots())

    caches = findings_of(payload, "tool_cache")
    assert list(caches) == [str(tree.uv)]
    assert caches[str(tree.uv)]["details"]["tool"] == "uv"


def test_tool_cache_inside_a_root_counts_zero(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    _, payload = run_map(monkeypatch, world, [*tree.roots(), world.home / ".cache"])

    uv = unit(payload, "tool_cache", tree.uv)
    assert uv["details"]["overlap"] == "inside_scan_root"
    assert uv["details"]["counted_allocated_bytes"] == 0


def test_npm_location_comes_from_configuration_and_npm_never_runs(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    tree = build(world)
    npm = world.home / ".npm"
    make_file(npm / "_cacache" / "index", 5_000)
    _, payload = run_map(monkeypatch, world, tree.roots())

    found = unit(payload, "tool_cache", npm)
    assert found["details"]["tool"] == "npm"
    assert found["details"]["counted_allocated_bytes"] == expected_allocated(npm)
    assert all(call[0] != "npm" for call in world.runner.calls)


def test_unavailable_tools_do_not_make_the_result_partial(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = world.home / "Documents"
    make_file(root / "f.bin", 1000)
    _, payload = run_map(monkeypatch, world, [root])

    sources = {s["source"]: s["reason"] for s in payload["meta"]["unavailable_sources"]}
    assert sources["uv"] == sources["brew"] == "not_installed"
    assert payload["meta"]["status"] == "complete"


def test_injected_category_paths_replace_the_defaults(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    special = world.home / "Special"
    make_file(special / "s.bin", 3000)
    world.categories = (CategorySpec("Special", str(special)),)
    root = world.home / "Documents"
    make_file(root / "f.bin", 1000)
    _, payload = run_map(monkeypatch, world, [root])

    assert list(findings_of(payload, "category")) == [str(special)]


def test_default_categories_follow_the_catalog() -> None:
    specs = default_categories("/Users/x", "/System/Volumes/Data")

    assert [s.label for s in specs] == [
        "User caches",
        "Application support",
        "App containers",
        "Group containers",
        "Developer data",
        "Device backups (inside Application support)",
        "Mail",
        "Messages",
        "Downloads",
        "Applications",
    ]
    assert specs[0].path == "/System/Volumes/Data/Users/x/Library/Caches"
    assert specs[-1].path == "/System/Volumes/Data/Applications"
    assert [s.label for s in default_categories("", "/M")] == ["Applications"]
