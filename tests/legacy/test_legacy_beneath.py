"""Legacy hashing reads beneath the scan root, so swapped parents cannot redirect."""

import os
import shutil
from pathlib import Path

import pytest

from byte_census.legacy import scan
from byte_census.legacy.hashing import calculate_hash
from byte_census.legacy.scan import find_duplicates_compare, find_duplicates_single


def _swap_parent_for_symlink(
    monkeypatch: pytest.MonkeyPatch, parent: Path, outside: Path
) -> None:
    """After collection, replace parent with a symlink to the outside directory."""
    real = scan._repeated_size_candidates

    def swapping(size_groups: dict[int, list[Path]]) -> list[Path]:
        candidates = real(size_groups)
        shutil.rmtree(parent)
        parent.symlink_to(outside)
        return candidates

    monkeypatch.setattr(scan, "_repeated_size_candidates", swapping)


def test_swapped_parent_never_hashes_the_outside_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"same")
    (root / "sub" / "b.txt").write_bytes(b"same")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "b.txt").write_bytes(b"same")
    _swap_parent_for_symlink(monkeypatch, root / "sub", outside)

    duplicates, errors, _ = find_duplicates_single(root, quiet=True)

    assert duplicates == {}
    assert len(errors) == 1 and "b.txt" in errors[0]


def test_compare_mode_uses_each_sides_own_root(tmp_path: Path) -> None:
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "x.txt").write_bytes(b"same")
    (right / "y.txt").write_bytes(b"same")

    duplicates, errors, _ = find_duplicates_compare(left, right, quiet=True)

    assert errors == []
    assert [sorted(p.name for p in v) for v in duplicates.values()] == [
        ["x.txt", "y.txt"]
    ]


def test_symlinked_root_path_is_resolved_before_hashing(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "a.txt").write_bytes(b"hello")
    alias = tmp_path / "alias"
    alias.symlink_to(real_root)
    digest = calculate_hash(alias / "a.txt", root=alias)
    assert digest == calculate_hash(real_root / "a.txt")


def test_changed_inode_since_collection_is_a_read_error(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"hello")
    expected = os.lstat(path)
    path.unlink()
    path.write_bytes(b"other")
    other = tmp_path / "b.txt"
    other.write_bytes(b"hello")
    stale = os.lstat(other)
    with pytest.raises(OSError, match="Cannot read file"):
        calculate_hash(path, root=tmp_path, expected=stale)
    assert expected is not None
