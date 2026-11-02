"""Golden parity with the replaced collector (WI-DISK-MAP-TREE AC-02, AC-03).

The golden files in tests/fixtures/parity were produced once, manually, from
storage-inventory.sh and `du -k -d 4` on the tree that
tests.support.parity_fixture builds (see PROVENANCE.md). These tests never
run those programs: they rebuild the same tree in tmp_path, run byte-census
on it, and compare the relationships the golden output fixes. Sizes are
compared with independent `lstat` totals of the rebuilt tree, because block
allocation of a rebuilt tree is not guaranteed to match the original run.

Compared (parity matrix retain rows):
- S6: the set and order of first-level folders of each scan root.
- S8: the set and order of large files (logical size, threshold 1 MiB).
- S18: no root is nested; each root counts in the reconciliation.
- S19, S20: which categories exist, their labels and paths, and which are
  counted or shown only (inside a scan root or nested); Applications is
  excluded because the golden run measured the real /Applications.
- P14: the folder tree has exactly the folders `du -k -d 4` lists.
Not compared: kilobyte values (rebuilt tree), df, diskutil, snapshot and
Docker values (machine-specific), human units, and record wording.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from tests.support.disk_map_world import (
    FakeRunner,
    World,
    expected_allocated,
    findings_of,
    run_map,
)
from tests.support.parity_fixture import build_parity_fixture

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "parity"
PLACEHOLDER = "<FIXTURE>/"
SHOWN_ONLY = {"equals_scan_root", "inside_scan_root", "inside_category"}


def golden_rows(name: str) -> list[list[str]]:
    lines = (GOLDEN / name).read_text(encoding="utf-8").splitlines()
    return [line.split("\t") for line in lines[1:]]


def relative(target: str) -> str:
    assert target.startswith(PLACEHOLDER), target
    return target[len(PLACEHOLDER) :]


def golden_section(name: str, section: str, under: str | None = None) -> list[str]:
    return [
        relative(row[1])
        for row in golden_rows(name)
        if row[0] == section
        and (under is None or row[3] == f"under {PLACEHOLDER}{under}")
    ]


@pytest.fixture
def parity(tmp_path: Path) -> tuple[World, Path]:
    data = tmp_path.resolve() / "data"
    base = data / "fixture"
    _, home = build_parity_fixture(base)
    return World(data, home, FakeRunner()), base


def ours(payload: dict[str, Any], kind: str, base: Path) -> list[str]:
    return [
        os.path.relpath(f["target"], base)
        for f in payload["data"]["findings"]
        if f["kind"] == kind
    ]


SCAN = "storage-inventory--scan--inventory.tsv"
CATEGORIES = "storage-inventory--categories--inventory.tsv"


def test_first_level_folders_match_the_collector(
    monkeypatch: pytest.MonkeyPatch, parity: tuple[World, Path]
) -> None:
    world, base = parity
    _, payload = run_map(
        monkeypatch,
        world,
        [base / "scan"],
        "--skip-categories",
        "--large-file-min",
        "1",
    )

    assert ours(payload, "first_level", base) == golden_section(SCAN, "first-level")
    for target, found in findings_of(payload, "first_level").items():
        assert found["allocated_bytes"] == expected_allocated(Path(target))
    root = findings_of(payload, "root_total")[str(base / "scan")]
    assert golden_section(SCAN, "scan-root") == ["scan"]
    assert root["allocated_bytes"] == expected_allocated(base / "scan")
    assert root["details"]["counted_allocated_bytes"] == root["allocated_bytes"]


def test_large_files_match_the_collector(
    monkeypatch: pytest.MonkeyPatch, parity: tuple[World, Path]
) -> None:
    world, base = parity
    _, payload = run_map(
        monkeypatch,
        world,
        [base / "scan"],
        "--skip-categories",
        "--large-file-min",
        "1",
    )

    assert ours(payload, "large_file", base) == golden_section(SCAN, "large-file")
    for target, found in findings_of(payload, "large_file").items():
        assert found["logical_bytes"] == os.lstat(target).st_size


def test_tree_matches_du_depth_4(
    monkeypatch: pytest.MonkeyPatch, parity: tuple[World, Path]
) -> None:
    world, base = parity
    _, payload = run_map(
        monkeypatch, world, [base / "scan"], "--skip-categories", "--tree-min-mb", "0"
    )

    lines = (GOLDEN / "du-k-d4--scan.txt").read_text(encoding="utf-8").splitlines()
    expected = {relative(line.split("\t", 1)[1]) for line in lines}
    found: dict[str, int] = {}

    def visit(node: dict[str, Any], parent: str | None) -> None:
        name = os.path.relpath(node["path"], base)
        if parent is not None:
            assert os.path.dirname(name) == parent
        found[name] = node["allocated_bytes"]
        for child in node["children"]:
            visit(child, name)

    visit(payload["data"]["tree"]["roots"][0], None)
    assert set(found) == expected
    for name, allocated in found.items():
        assert allocated == expected_allocated(base / name)


def test_categories_match_the_collector(
    monkeypatch: pytest.MonkeyPatch, parity: tuple[World, Path]
) -> None:
    world, base = parity
    support = base / "home" / "Library" / "Application Support"
    _, payload = run_map(monkeypatch, world, [base / "scan", support])

    rows = [r for r in golden_rows(CATEGORIES) if r[0] == "category"]
    golden = {
        relative(r[1]): (r[3].split(" errors=")[0], r[3].endswith("counted=1"))
        for r in rows
        if r[1] != "/Applications"
    }
    found = {
        os.path.relpath(target, base): (
            f["details"]["label"],
            f["details"]["overlap"] not in SHOWN_ONLY,
        )
        for target, f in findings_of(payload, "category").items()
    }
    assert found == golden
    for target, f in findings_of(payload, "category").items():
        assert f["allocated_bytes"] == expected_allocated(Path(target))
    nested = [r[3] for r in golden_rows(CATEGORIES) if r[0] == "scan-root"]
    assert all("nested=0" in note for note in nested)
    roots = findings_of(payload, "root_total").values()
    assert all(r["details"]["overlap"] is None for r in roots)
