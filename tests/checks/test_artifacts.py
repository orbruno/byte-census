"""Tests for `byte-census artifacts scan` (WI-ARTIFACTS)."""

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from byte_census.cli import main
from byte_census.model import finding_id
from tests.support.snapshots import allocated_bytes_of, assert_json_snapshot

CLONE_CAVEAT = "apfs_clone_or_shared_extent"


def write(path: Path, size: int = 10) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def scan(root: Path, *extra: str) -> Result:
    return CliRunner().invoke(main, ["artifacts", "scan", str(root), *extra])


def scan_json(root: Path) -> dict[str, Any]:
    result = scan(root)
    assert result.exit_code == 0, result.stderr
    return json.loads(result.stdout)


def targets(payload: dict[str, Any]) -> list[str]:
    return [f["target"] for f in payload["data"]["findings"]]


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = (tmp_path / "projects").resolve()
    write(root / "web" / "node_modules" / "pkg" / "index.js", 5000)
    write(root / "web" / "package.json", 20)
    write(root / "api" / ".venv" / "lib" / "site.py", 3000)
    write(root / "api" / "pyproject.toml", 20)
    write(root / "old" / "venv" / "bin" / "python", 100)
    write(root / "rust" / "Cargo.toml", 20)
    write(root / "rust" / "target" / "debug" / "app", 9000)
    for project in ("web", "api", "old", "rust"):
        os.utime(root / project, (1_700_000_000, 1_700_000_000))
    return root


def test_snapshot_happy_path(tree: Path) -> None:
    payload = scan_json(tree)
    # Suggestions are ordered by hash-derived id, which depends on the tmp
    # path; the snapshot lists them in finding order instead.
    finding_order = [f["id"] for f in payload["data"]["findings"]]
    payload["data"]["suggestions"].sort(
        key=lambda s: finding_order.index(s["finding_ids"][0])
    )

    for suggestion in payload["data"]["suggestions"]:
        # The helper masks only strings that start with the root; the
        # command embeds it after `rm -rf -- '`.
        suggestion["command"] = suggestion["command"].replace(str(tree), "<ROOT>")

    assert_json_snapshot(payload, "artifacts-scan", roots=[tree])


def test_suggestions_ordered_by_risk_then_id(tree: Path) -> None:
    suggestions = scan_json(tree)["data"]["suggestions"]

    ids = [s["id"] for s in suggestions]
    assert ids == sorted(ids)


def test_lists_all_four_kinds_with_regenerate_commands(tree: Path) -> None:
    findings = scan_json(tree)["data"]["findings"]

    by_kind = {f["details"]["artifact_kind"]: f for f in findings}
    assert set(by_kind) == {"node_modules", ".venv", "venv", "target"}
    commands = {k: f["details"]["regenerate_command"] for k, f in by_kind.items()}
    assert commands == {
        "node_modules": "npm install",
        ".venv": "uv sync",
        "venv": "uv sync",
        "target": "cargo build",
    }
    node = by_kind["node_modules"]
    assert node["kind"] == "artifact"
    assert node["details"]["project"] == str(tree / "web")
    assert node["id"] == finding_id("art", "artifact", node["target"])
    assert node["caveats"] == [CLONE_CAVEAT]
    assert node["reclaimable_estimate_bytes"] == node["allocated_bytes"]


def test_sizes_match_lstat_and_summary_sums(tree: Path) -> None:
    payload = scan_json(tree)

    node = tree / "web" / "node_modules"
    expected = allocated_bytes_of(node) + allocated_bytes_of(node / "pkg")
    expected += allocated_bytes_of(node / "pkg" / "index.js")
    finding = next(f for f in payload["data"]["findings"] if f["target"] == str(node))
    assert finding["allocated_bytes"] == expected
    assert finding["logical_bytes"] == 5000
    total = sum(f["allocated_bytes"] for f in payload["data"]["findings"])
    assert payload["data"]["summary"] == {
        "artifact_count": 4,
        "total_allocated_bytes": total,
    }


def test_findings_ordered_by_size_descending(tree: Path) -> None:
    sizes = [f["allocated_bytes"] for f in scan_json(tree)["data"]["findings"]]

    assert sizes == sorted(sizes, reverse=True)


def test_project_mtime_is_project_directory_mtime(tree: Path) -> None:
    project = tree / "web"
    os.utime(project, (1_700_000_000, 1_700_000_000))

    findings = scan_json(tree)["data"]["findings"]

    node = next(f for f in findings if f["details"]["artifact_kind"] == "node_modules")
    assert node["details"]["project_mtime"] == "2023-11-14T22:13:20Z"


def test_target_without_cargo_toml_is_not_an_artifact(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    write(root / "plain" / "target" / "file.txt")
    write(root / "plain" / "target" / "node_modules" / "x.js")

    payload = scan_json(root)

    assert targets(payload) == [str(root / "plain" / "target" / "node_modules")]


def test_does_not_descend_into_found_artifacts(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    write(root / "app" / "node_modules" / "dep" / "node_modules" / "inner.js", 50)

    payload = scan_json(root)

    assert targets(payload) == [str(root / "app" / "node_modules")]


@pytest.mark.parametrize("skipped", [".git", "Library", ".Trash"])
def test_does_not_descend_into_excluded_directories(
    tmp_path: Path, skipped: str
) -> None:
    root = tmp_path.resolve()
    write(root / skipped / "proj" / "node_modules" / "a.js")
    write(root / "keep" / "node_modules" / "a.js")

    payload = scan_json(root)

    assert targets(payload) == [str(root / "keep" / "node_modules")]


def test_does_not_follow_symlinks(tmp_path: Path) -> None:
    root = (tmp_path / "root").resolve()
    outside = write(tmp_path / "outside" / "node_modules" / "a.js").parent.parent
    root.mkdir()
    (root / "link").symlink_to(outside)
    (root / "node_modules").symlink_to(outside / "node_modules")
    write(root / "real" / "venv" / "a.py")

    payload = scan_json(root)

    assert targets(payload) == [str(root / "real" / "venv")]


def test_symlink_inside_artifact_is_counted_not_followed(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    big = write(root / "elsewhere" / "big.bin", 100_000)
    artifact = root / "app" / "node_modules"
    write(artifact / "a.js", 10)
    (artifact / "link").symlink_to(big)

    finding = scan_json(root)["data"]["findings"][0]

    assert finding["target"] == str(artifact)
    assert finding["logical_bytes"] == 10
    expected = allocated_bytes_of(artifact) + allocated_bytes_of(artifact / "a.js")
    expected += allocated_bytes_of(artifact / "link")
    assert finding["allocated_bytes"] == expected


def test_empty_tree_reports_no_findings(tmp_path: Path) -> None:
    payload = scan_json(tmp_path.resolve())

    assert payload["data"]["findings"] == []
    assert payload["data"]["summary"] == {
        "artifact_count": 0,
        "total_allocated_bytes": 0,
    }
    assert payload["meta"]["status"] == "complete"


def test_each_artifact_has_medium_risk_suggestion(tree: Path) -> None:
    data = scan_json(tree)["data"]

    assert len(data["suggestions"]) == 4
    by_id = {s["id"]: s for s in data["suggestions"]}
    for finding in data["findings"]:
        (sid,) = finding["suggestion_ids"]
        suggestion = by_id[sid]
        assert sid == f"artifact-remove-regenerate@{finding['id']}"
        assert suggestion["risk"] == "medium"
        assert suggestion["reversible"] is False
        assert suggestion["finding_ids"] == [finding["id"]]
        regenerate = finding["details"]["regenerate_command"]
        assert suggestion["command"].startswith(f"rm -rf -- '{finding['target']}' ")
        assert suggestion["command"].endswith(f"&& {regenerate}")


def test_hard_links_across_artifacts_are_attributed_in_sorted_order(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    shared = write(root / "a" / "node_modules" / "shared.bin", 40_000)
    other = root / "b" / ".venv" / "shared.bin"
    other.parent.mkdir(parents=True)
    os.link(shared, other)
    file_blocks = allocated_bytes_of(shared)

    payload = scan_json(root)

    findings = {f["target"]: f for f in payload["data"]["findings"]}
    first = findings[str(root / "a" / "node_modules")]
    second = findings[str(root / "b" / ".venv")]
    assert second["allocated_bytes"] - allocated_bytes_of(second["target"]) == (
        file_blocks
    )
    assert first["caveats"] == [CLONE_CAVEAT, "hard_links_merged"]
    assert second["caveats"] == [CLONE_CAVEAT, "hard_links_merged"]
    shown = first["allocated_bytes"] + second["allocated_bytes"]
    assert payload["data"]["summary"]["total_allocated_bytes"] == shown - file_blocks


def test_hard_links_inside_one_artifact_count_once(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    artifact = root / "p" / "node_modules"
    first = write(artifact / "one.bin", 30_000)
    os.link(first, artifact / "two.bin")

    finding = scan_json(root)["data"]["findings"][0]

    assert finding["logical_bytes"] == 30_000
    assert finding["allocated_bytes"] == allocated_bytes_of(
        artifact
    ) + allocated_bytes_of(first)
    assert finding["caveats"] == [CLONE_CAVEAT, "hard_links_merged"]


def test_repeated_runs_give_identical_output(tree: Path) -> None:
    first = scan_json(tree)
    second = scan_json(tree)

    for payload in (first, second):
        payload["meta"]["captured_at"] = ""
        payload["meta"]["cost"]["elapsed_s"] = 0
    assert first == second


@pytest.fixture
def locked(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path.resolve()
    write(root / "ok" / "node_modules" / "a.js")
    write(root / "ok" / "node_modules" / "private" / "b.js")
    write(root / "closed" / "x.txt")
    locked_dirs = [root / "ok" / "node_modules" / "private", root / "closed"]
    for directory in locked_dirs:
        directory.chmod(0)
    try:
        yield root
    finally:
        for directory in locked_dirs:
            directory.chmod(0o755)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_unreadable_entries_go_to_incomplete_coverage(locked: Path) -> None:
    payload = scan_json(locked)

    assert payload["meta"]["status"] == "partial"
    coverage = {c["path"]: c for c in payload["meta"]["incomplete_coverage"]}
    assert set(coverage) == {
        str(locked / "closed"),
        str(locked / "ok" / "node_modules" / "private"),
    }
    for entry in coverage.values():
        assert entry["reason"] == "permission_denied"
        assert entry["errno"] == "EACCES"
        assert entry["operation"] == "scandir"
    assert targets(payload) == [str(locked / "ok" / "node_modules")]


def test_vanished_artifact_is_reported_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from byte_census.checks import artifacts

    root = tmp_path.resolve()
    gone = write(root / "p" / "node_modules" / "a.js").parent
    write(root / "q" / ".venv" / "a.py")
    real_measure = artifacts.measure_artifact

    def measure(path: str, claimed: frozenset[tuple[int, int]]) -> Any:
        if path == str(gone):
            for child in gone.iterdir():
                child.unlink()
            gone.rmdir()
        return real_measure(path, claimed)

    monkeypatch.setattr(artifacts, "measure_artifact", measure)

    payload = scan_json(root)

    assert targets(payload) == [str(root / "q" / ".venv")]
    (entry,) = payload["meta"]["incomplete_coverage"]
    assert entry["path"] == str(gone)
    assert entry["reason"] == "vanished"
    assert entry["errno"] == "ENOENT"


def test_scope_cost_and_options(tree: Path) -> None:
    payload = scan_json(tree)

    (root,) = payload["meta"]["scope"]["roots"]
    assert root["path"] == str(tree)
    assert root["st_dev"] == os.lstat(tree).st_dev
    assert payload["meta"]["scope"]["options"] == {}
    assert payload["meta"]["command"] == "artifacts scan"
    cost = payload["meta"]["cost"]
    assert cost["entries_visited"] >= 10
    assert cost["content_bytes_read"] == 0
    assert cost["subprocess_calls"] == 0


def test_table_format(tree: Path) -> None:
    result = scan(tree, "--format", "table")

    assert result.exit_code == 0
    assert "node_modules" in result.stdout


def test_nonexistent_root_exits_3(tmp_path: Path) -> None:
    result = scan(tmp_path / "missing")

    assert result.exit_code == 3
    assert json.loads(result.stderr)["code"] == "validation_error"
    assert result.stdout == ""


def test_file_as_root_exits_3(tmp_path: Path) -> None:
    result = scan(write(tmp_path / "file.txt"))

    assert result.exit_code == 3


def test_missing_root_argument_exits_2() -> None:
    result = CliRunner().invoke(main, ["artifacts", "scan"])

    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "usage_error"


def test_internal_failure_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from byte_census.checks import artifacts

    def boom(root: str) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(artifacts, "discover", boom)

    result = scan(tmp_path)

    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "internal_error"


@pytest.mark.parametrize("flag", ["-h", "--help"])
@pytest.mark.parametrize("args", [["artifacts"], ["artifacts", "scan"]])
def test_help_has_usage_and_example(args: list[str], flag: str) -> None:
    result = CliRunner().invoke(main, [*args, flag])

    assert result.exit_code == 0
    assert result.output.startswith("Usage:")
    assert "Example:" in result.output
