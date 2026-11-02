"""Directory enumeration for dupfind goes through fsread (read-only walk)."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from byte_census import fsread
from byte_census.legacy.dupfind import find
from byte_census.legacy.scan import collect_files, find_duplicates_single


def _tree(root: Path) -> None:
    (root / "sub").mkdir()
    (root / "a.txt").write_bytes(b"same")
    (root / "sub" / "b.txt").write_bytes(b"same")
    (root / "link.txt").symlink_to(root / "a.txt")


def test_recursive_collects_sorted_regular_files_only(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert collect_files(tmp_path) == [tmp_path / "a.txt", tmp_path / "sub" / "b.txt"]


def test_non_recursive_lists_top_level_only(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert collect_files(tmp_path, recursive=False) == [tmp_path / "a.txt"]


def test_min_size_filter_is_kept(tmp_path: Path) -> None:
    _tree(tmp_path)
    (tmp_path / "big.bin").write_bytes(b"x" * 10)
    assert collect_files(tmp_path, min_size=5) == [tmp_path / "big.bin"]


def test_dataless_directory_is_never_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path)
    evicted = str(tmp_path / "sub")
    real_entry_lstat = fsread._entry_lstat

    class Info:
        def __init__(self, info: os.stat_result) -> None:
            self.st_mode = info.st_mode
            self.st_dev = info.st_dev
            self.st_flags = fsread.SF_DATALESS

    def fake(entry: os.DirEntry[str]) -> object:
        info = real_entry_lstat(entry)
        return Info(info) if entry.path == evicted else info

    real_scandir = os.scandir

    def guarded(path: object = ".") -> object:
        assert os.fspath(path) != evicted, "dataless directory was listed"  # type: ignore[arg-type]
        return real_scandir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(fsread, "_entry_lstat", fake)
    monkeypatch.setattr(os, "scandir", guarded)
    duplicates, errors, _ = find_duplicates_single(tmp_path, quiet=True)
    assert duplicates == {}
    assert any("sub" in message for message in errors)


def test_foreign_device_subdirectory_is_not_descended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _tree(tmp_path)
    foreign = str(tmp_path / "sub")
    real_entry_lstat = fsread._entry_lstat

    class Info:
        def __init__(self, info: os.stat_result) -> None:
            self.st_mode = info.st_mode
            self.st_dev = info.st_dev + 1
            self.st_flags = 0

    def fake(entry: os.DirEntry[str]) -> object:
        info = real_entry_lstat(entry)
        return Info(info) if entry.path == foreign else info

    monkeypatch.setattr(fsread, "_entry_lstat", fake)
    assert collect_files(tmp_path) == [tmp_path / "a.txt"]


def test_unreadable_directory_is_a_warning_and_exit_0(tmp_path: Path) -> None:
    _tree(tmp_path)
    (tmp_path / "sub").chmod(0)
    try:
        result = CliRunner().invoke(find, [str(tmp_path), "--quiet"])
    finally:
        (tmp_path / "sub").chmod(0o755)
    assert result.exit_code == 0, result.output
    assert "sub" in result.stderr
