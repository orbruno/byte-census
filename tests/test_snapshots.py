"""Tests for the JSON snapshot helper."""

import json
import os
from pathlib import Path

import pytest

from tests.support import snapshots
from tests.support.snapshots import allocated_bytes_of, assert_json_snapshot, normalize


@pytest.fixture
def snap_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path)
    monkeypatch.delenv(snapshots.UPDATE_ENV, raising=False)
    return tmp_path


def test_normalize_replaces_volatile_meta_fields() -> None:
    data = {
        "meta": {
            "captured_at": "2026-11-02T10:00:00Z",
            "cost": {"files": 3},
            "scope": {"st_dev": 16777234, "kept": 1},
        },
        "other": {"st_dev": 5},
    }

    result = normalize(data)

    assert result["meta"]["captured_at"] == "<CAPTURED_AT>"
    assert result["meta"]["cost"] == "<COST>"
    assert result["meta"]["scope"] == {"st_dev": "<ST_DEV>", "kept": 1}
    assert result["other"] == {"st_dev": 5}
    assert data["meta"]["cost"] == {"files": 3}


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
