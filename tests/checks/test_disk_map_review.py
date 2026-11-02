"""Tests for the disk map review fixes (identity, nested large files, df
parsing, sparse caveat, unobserved nested roots, shared ledger)."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from byte_census.checks import disk_map_reconcile
from byte_census.checks.disk_map_reconcile import DfFormatError, parse_df
from byte_census.checks.disk_map_walk import Ledger
from tests.support.disk_map_world import (
    DF_ARGV,
    DF_HEADER,
    MIB,
    World,
    expected_allocated,
    findings_of,
    make_file,
    make_sparse,
    new_world,
    run_map,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return new_world(tmp_path)


def docs_tree(world: World) -> Path:
    docs = world.home / "Docs"
    make_file(docs / "big" / "a.bin", 300_000)
    make_file(docs / "small" / "b.bin", 20_000)
    return docs


def case_insensitive(path: Path) -> bool:
    return (path.parent / path.name.swapcase()).exists()


# P1: identity, not spelling


@pytest.mark.parametrize("order", [0, 1])
def test_case_alias_roots_merge_and_count_once(
    monkeypatch: pytest.MonkeyPatch, world: World, order: int
) -> None:
    docs = docs_tree(world)
    if not case_insensitive(docs):
        pytest.skip("tmp_path is on a case-sensitive volume; no case aliases exist")
    alias = world.home / "docs"
    given = [docs, alias] if order == 0 else [alias, docs]
    _, payload = run_map(monkeypatch, world, given)

    roots = findings_of(payload, "root_total")
    assert list(roots) == [str(docs)]
    assert roots[str(docs)]["details"]["given"] == str(given[0])
    assert payload["meta"]["scope"]["roots"][0]["path"] == str(docs)
    assert payload["data"]["summary"]["measured_allocated_bytes"] == (
        expected_allocated(docs)
    )


@pytest.mark.parametrize("order", [0, 1])
def test_case_alias_nested_root_is_not_walked_twice(
    monkeypatch: pytest.MonkeyPatch, world: World, order: int
) -> None:
    docs = docs_tree(world)
    if not case_insensitive(docs):
        pytest.skip("tmp_path is on a case-sensitive volume; no case aliases exist")
    inner_alias = world.home / "DOCS" / "BIG"
    given = [docs, inner_alias] if order == 0 else [inner_alias, docs]
    _, payload = run_map(monkeypatch, world, given)

    roots = findings_of(payload, "root_total")
    inner = roots[str(docs / "big")]
    assert inner["details"]["overlap"] == "inside_scan_root"
    assert inner["details"]["counted_allocated_bytes"] == 0
    assert inner["details"]["given"] == str(inner_alias)
    assert inner["allocated_bytes"] == expected_allocated(docs / "big")
    assert payload["data"]["summary"]["measured_allocated_bytes"] == (
        expected_allocated(docs)
    )


@pytest.mark.parametrize("order", [0, 1])
def test_roots_with_one_identity_merge_whatever_their_spelling(
    monkeypatch: pytest.MonkeyPatch, world: World, order: int
) -> None:
    first = docs_tree(world)
    second = world.home / "Other"
    make_file(second / "c.bin", 50_000)
    real = os.lstat
    twin = real(first)

    def lstat(path: Any) -> Any:
        info = real(path)
        if os.fspath(path) != str(second):
            return info
        return os.stat_result((info.st_mode, twin.st_ino, twin.st_dev, *info[3:10]))

    world.lstat = lstat
    given = [first, second] if order == 0 else [second, first]
    _, payload = run_map(monkeypatch, world, given)

    roots = findings_of(payload, "root_total")
    assert len(roots) == 1
    assert payload["data"]["summary"]["root_count"] == 1
    assert next(iter(roots.values()))["details"]["given"] == str(given[0])


def test_ledger_counts_an_inode_reached_twice_once(tmp_path: Path) -> None:
    info = os.lstat(make_file(tmp_path / "f.bin", 10_000))
    ledger = Ledger()

    assert ledger.claim(info) == info.st_blocks * 512
    assert ledger.claim(info) == 0
    assert ledger.allocated_bytes == info.st_blocks * 512


# P2: nested roots select their own large files


def test_nested_root_keeps_its_own_largest_files(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    outer = world.home / "outer"
    for index in range(20):
        make_file(outer / "a" / f"big{index:02d}.bin", 10_000 + index)
    inner = outer / "b"
    make_file(inner / "small1.bin", 100)
    make_file(inner / "small2.bin", 200)
    _, payload = run_map(monkeypatch, world, [outer, inner], "--large-file-min", "0")

    large = [f for f in payload["data"]["findings"] if f["kind"] == "large_file"]
    owners = {f["target"]: f["details"]["root"] for f in large}
    assert owners[str(inner / "small2.bin")] == str(inner)
    assert owners[str(inner / "small1.bin")] == str(inner)
    assert sum(1 for root in owners.values() if root == str(outer)) == 20
    ids = [f["id"] for f in payload["data"]["findings"]]
    assert len(ids) == len(set(ids))


# P2: df output is validated


def df_text(row: str, header: str = DF_HEADER) -> str:
    return header + row + "\n"


ROW = "/dev/disk3s5 1000 600 400 60% 1 2 0%   /System/Volumes/Data"


def test_parse_df_reads_columns_by_position_with_a_numeric_filesystem_name() -> None:
    usage = parse_df(
        df_text("map 123 456 1000 600 400 60% 1 2 0%   /System/Volumes/Data")
    )

    assert (usage.total_bytes, usage.used_bytes, usage.available_bytes) == (
        1000 * 1024,
        600 * 1024,
        400 * 1024,
    )


def test_parse_df_accepts_the_header_without_inode_columns() -> None:
    header = "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
    usage = parse_df(
        df_text("/dev/disk3s5 1000 600 400 60% /System/Volumes/Data", header)
    )

    assert usage.used_bytes == 600 * 1024


@pytest.mark.parametrize(
    "text",
    [
        df_text(ROW, DF_HEADER.replace("1024-blocks", "512-blocks")),
        df_text(ROW.replace(" 600 ", " 6x0 ")),
        df_text("/dev/disk3s5 1000 600 400 60%   /System/Volumes/Data"),
        df_text(ROW) + "/dev/disk9 1 1 1 1% 1 1 1%   /System/Volumes/Data\n",
        df_text(ROW.replace("/System/Volumes/Data", "/Volumes/Other")),
        df_text(ROW.replace("   /System", "/System")),
        ROW + "\n",
    ],
    ids=[
        "512-blocks",
        "malformed",
        "short-row",
        "extra-line",
        "mount",
        "glued",
        "no-header",
    ],
)
def test_parse_df_rejects_ambiguous_output(text: str) -> None:
    with pytest.raises(DfFormatError):
        parse_df(text)


def test_unusable_df_output_exits_4(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    world.runner.answers[DF_ARGV] = df_text(
        ROW, DF_HEADER.replace("1024-blocks", "512-blocks")
    )
    result, _ = run_map(monkeypatch, world, [docs_tree(world)])

    assert result.exit_code == 4
    assert "not usable" in json.loads(result.stderr)["reason"]
    assert disk_map_reconcile.DF_COMMAND in json.loads(result.stderr)["error"]


# P2: sparse files below the large-file threshold


def test_sparse_file_marks_its_root_and_first_level_folder(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = world.home / "vm"
    sparse = make_sparse(root / "disk" / "image.raw", 3 * MIB)
    if os.lstat(sparse).st_blocks * 512 >= 3 * MIB:
        pytest.skip("this filesystem does not create sparse files")
    make_file(root / "plain" / "f.bin", 1000)
    _, payload = run_map(monkeypatch, world, [root])

    assert findings_of(payload, "large_file") == {}
    assert "sparse_file" in findings_of(payload, "root_total")[str(root)]["caveats"]
    first = findings_of(payload, "first_level")
    assert first[str(root / "disk")]["caveats"] == ["sparse_file"]
    assert first[str(root / "plain")]["caveats"] == []


# Observation: a nested root hidden by an ancestor denial is unobserved


def test_nested_root_behind_a_denied_folder_is_unobserved(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    outer = world.home / "outer"
    locked = outer / "locked"
    inner = locked / "inner"
    make_file(inner / "f.bin", 1000)
    locked.chmod(0o311)
    try:
        result, payload = run_map(monkeypatch, world, [outer, inner])
    finally:
        locked.chmod(0o755)

    assert result.exit_code == 0, result.stderr
    found = findings_of(payload, "root_total")[str(inner)]
    assert found["allocated_bytes"] is None
    assert found["logical_bytes"] is None
    assert found["details"]["unobserved"] is True
    assert found["details"]["coverage_path"] == str(locked)
    assert found["details"]["counted_allocated_bytes"] == 0
    assert payload["meta"]["status"] == "partial"
