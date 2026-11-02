"""Tests for the JSON snapshot helper."""

import json
import os
from pathlib import Path

import pytest

from byte_census.model import finding_id
from tests.support import snapshots
from tests.support.snapshots import allocated_bytes_of, assert_json_snapshot, normalize


@pytest.fixture
def snap_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path)
    monkeypatch.delenv(snapshots.UPDATE_ENV, raising=False)
    return tmp_path


def test_normalize_masks_only_volatile_meta_fields() -> None:
    data = {
        "meta": {
            "captured_at": "2026-11-02T10:00:00Z",
            "cost": {"elapsed_s": 0.734, "entries_visited": 3, "notes": {}},
            "scope": {"st_dev": 16777234, "kept": 1},
        },
        "other": {"st_dev": 5},
    }

    result = normalize(data)

    assert result["meta"]["captured_at"] == "<CAPTURED_AT>"
    assert result["meta"]["cost"] == {
        "elapsed_s": "<ELAPSED_S>",
        "entries_visited": 3,
        "notes": {},
    }
    assert list(result["meta"]["cost"]) == ["elapsed_s", "entries_visited", "notes"]
    assert result["meta"]["scope"] == {"st_dev": "<ST_DEV>", "kept": 1}
    assert result["other"] == {"st_dev": 5}
    assert data["meta"]["cost"]["elapsed_s"] == 0.734


def test_normalize_masks_st_dev_only_when_it_is_an_int() -> None:
    data = {"meta": {"scope": {"st_dev": None, "roots": [{"st_dev": "odd"}]}}}

    result = normalize(data)

    assert result["meta"]["scope"]["st_dev"] is None
    assert result["meta"]["scope"]["roots"][0]["st_dev"] == "odd"


def test_snapshot_comparison_checks_field_order(snap_dir: Path) -> None:
    (snap_dir / "order.json").write_text(json.dumps({"b": 1, "a": 2}, indent=2) + "\n")

    assert_json_snapshot({"b": 1, "a": 2}, "order")
    with pytest.raises(AssertionError, match="mismatch"):
        assert_json_snapshot({"a": 2, "b": 1}, "order")


def test_normalize_replaces_fixture_root_prefix_in_nested_strings() -> None:
    data = {"paths": ["/tmp/fx/a/b.txt", {"p": "/tmp/fx"}], "n": 1, "s": "/other/x"}

    result = normalize(data, roots=["/tmp/fx"])

    assert result == {
        "paths": ["<ROOT>/a/b.txt", {"p": "<ROOT>"}],
        "n": 1,
        "s": "/other/x",
    }


def test_matching_snapshot_passes(snap_dir: Path) -> None:
    (snap_dir / "ok.json").write_text(
        json.dumps({"a": 1}, indent=2, sort_keys=True) + "\n"
    )

    assert_json_snapshot({"a": 1}, "ok")


def test_mismatch_fails(snap_dir: Path) -> None:
    (snap_dir / "bad.json").write_text(json.dumps({"a": 1}) + "\n")

    with pytest.raises(AssertionError, match="bad"):
        assert_json_snapshot({"a": 2}, "bad")


def test_missing_snapshot_fails_without_update_mode(snap_dir: Path) -> None:
    with pytest.raises(AssertionError, match="missing"):
        assert_json_snapshot({"a": 1}, "absent")

    assert not (snap_dir / "absent.json").exists()


def test_update_mode_writes_then_compares(
    snap_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(snapshots.UPDATE_ENV, "1")

    assert_json_snapshot({"b": [1, 2]}, "fresh")

    written = json.loads((snap_dir / "fresh.json").read_text())
    assert written == {"b": [1, 2]}
    monkeypatch.delenv(snapshots.UPDATE_ENV)
    assert_json_snapshot({"b": [1, 2]}, "fresh")


def test_update_mode_stores_normalized_data(
    snap_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(snapshots.UPDATE_ENV, "1")

    assert_json_snapshot({"p": "/tmp/fx/a"}, "norm", roots=["/tmp/fx"])

    assert json.loads((snap_dir / "norm.json").read_text()) == {"p": "<ROOT>/a"}


def test_update_env_other_than_one_is_not_update_mode(
    snap_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(snapshots.UPDATE_ENV, "0")

    with pytest.raises(AssertionError, match="missing"):
        assert_json_snapshot({}, "nope")


def test_allocated_bytes_of_uses_lstat_blocks(tmp_path: Path) -> None:
    target = tmp_path / "f.bin"
    target.write_bytes(b"x" * 5000)

    assert allocated_bytes_of(target) == os.lstat(target).st_blocks * 512
    assert allocated_bytes_of(str(target)) == allocated_bytes_of(target)


def test_allocated_bytes_of_does_not_follow_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "big.bin"
    target.write_bytes(b"x" * 100_000)
    link = tmp_path / "link"
    link.symlink_to(target)

    assert allocated_bytes_of(link) == os.lstat(link).st_blocks * 512


def test_normalize_masks_st_dev_of_every_scope_root() -> None:
    data = {
        "meta": {
            "scope": {
                "roots": [
                    {"path": "/a", "given": "a", "st_dev": 1},
                    {"path": "/b", "given": "b", "st_dev": 2},
                ]
            }
        }
    }

    result = normalize(data)

    assert [root["st_dev"] for root in result["meta"]["scope"]["roots"]] == [
        "<ST_DEV>",
        "<ST_DEV>",
    ]
    assert data["meta"]["scope"]["roots"][0]["st_dev"] == 1


def _finding(prefix: str, kind: str, target: str, **extra: object) -> dict:
    return {
        "id": finding_id(prefix, kind, target),
        "kind": kind,
        "target": target,
        **extra,
    }


def test_normalize_replaces_ids_consistently_across_references() -> None:
    first = _finding("art", "artifact", "/p/a/node_modules")
    second = _finding("art", "artifact", "/p/b/.venv")
    one, two = first["id"], second["id"]
    first["suggestion_ids"] = [f"rm@{one}"]
    data = {
        "data": {
            "findings": [first, second],
            "suggestions": [
                {"id": f"rm@{one}", "finding_ids": [one, two]},
                {"id": "docker-image-prune", "finding_ids": []},
            ],
            "reconciliation": {"contributions": [{"finding_id": two}]},
            "other": one,
        }
    }

    result = normalize(data)["data"]

    assert result["findings"][0]["id"] == "art-<ID1>"
    assert result["findings"][0]["suggestion_ids"] == ["rm@art-<ID1>"]
    assert result["findings"][1]["id"] == "art-<ID2>"
    assert result["suggestions"][0] == {
        "id": "rm@art-<ID1>",
        "finding_ids": ["art-<ID1>", "art-<ID2>"],
    }
    assert result["suggestions"][1]["id"] == "docker-image-prune"
    assert result["reconciliation"]["contributions"][0]["finding_id"] == "art-<ID2>"
    assert result["other"] == one


def test_normalized_ids_do_not_depend_on_the_machine_path() -> None:
    first = {"data": {"findings": [_finding("map", "first_level", "/m1/x")]}}
    second = {"data": {"findings": [_finding("map", "first_level", "/m2/x")]}}

    assert normalize(first, roots=["/m1"]) == normalize(second, roots=["/m2"])


def test_normalize_rejects_a_finding_id_that_breaks_the_rule() -> None:
    bad = _finding("dup", "duplicate_group", "sha256:00")
    bad["id"] = "dup-000000000000"

    with pytest.raises(AssertionError, match="dup-000000000000"):
        normalize({"data": {"findings": [bad]}})


def test_roots_are_masked_inside_strings_and_longest_root_wins() -> None:
    roots = ("/tmp/fx", "/tmp/fx/nested")
    command = "rm -rf -- '/tmp/fx/nested/a' && cd -- '/tmp/fx/b'"
    masked = snapshots._replace_roots({"command": command}, roots)
    assert masked == {"command": "rm -rf -- '<ROOT>/a' && cd -- '<ROOT>/b'"}


def test_volatile_paths_are_masked_and_must_exist() -> None:
    data = {"meta": {"cost": {"elapsed_s": 1.0, "subprocess_stdout_bytes": 7}}}
    masked = normalize(data, volatile=["meta.cost.subprocess_stdout_bytes"])
    assert masked["meta"]["cost"]["subprocess_stdout_bytes"] == "<VOLATILE>"
    with pytest.raises(AssertionError, match="volatile path not found"):
        normalize(data, volatile=["meta.cost.missing"])
