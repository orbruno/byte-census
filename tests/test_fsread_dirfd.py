"""Descriptor-relative traversal and content opens (security review MEDIUM 1).

The proof-of-concept races are simulated deterministically: a hook inside the
walker's stat seam swaps a directory for a symlink between the moment it is
listed and the moment it (or a child) is opened.
"""

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from byte_census import fsread
from byte_census.fsread import (
    FsReadError,
    IdentityChangedError,
    SkippedMount,
    WalkEntry,
    WalkError,
    list_directory,
    walk,
)

CHANGED = "changed_during_scan"


def fake_stat(base: Any, **overrides: Any) -> SimpleNamespace:
    fields = {n: getattr(base, n) for n in dir(base) if n.startswith("st_")}
    return SimpleNamespace(**{**fields, **overrides})


def make_outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    (outside / "b").mkdir(parents=True)
    (outside / "secret.txt").write_text("secret")
    (outside / "b" / "secret.txt").write_text("secret")
    return outside


def swap_for_symlink(directory: Path, target: Path) -> None:
    os.rename(directory, directory.with_name(directory.name + "-moved"))
    os.symlink(target, directory)


def paths(items: list[Any]) -> list[str]:
    return [item.path for item in items]


def test_poc_directory_swapped_after_listing_is_not_followed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Proof of concept 1: `root/a` becomes a symlink after it was listed."""
    outside = make_outside(tmp_path)
    root = tmp_path / "root"
    (root / "a").mkdir(parents=True)
    (root / "a" / "inner.txt").write_text("inner")
    real = fsread._entry_lstat

    def swap_after_stat(entry: Any) -> Any:
        info = real(entry)
        if entry.path == str(root / "a"):
            swap_for_symlink(root / "a", outside)
        return info

    monkeypatch.setattr(fsread, "_entry_lstat", swap_after_stat)

    items = list(walk(root))

    assert not any(p.startswith(str(root / "a") + "/") for p in paths(items))
    errors = [i for i in items if isinstance(i, WalkError)]
    assert [(e.path, e.reason) for e in errors] == [(str(root / "a"), CHANGED)]


def test_poc_parent_swapped_while_listing_children_stays_inside(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Proof of concept 2: `root/a` is swapped while its child `b` is examined.

    Before the fix, `lstat(root/a/b)` followed the new symlink and the walk
    listed `outside/b`, yielding `root/a/b/secret.txt` from outside the root.
    """
    outside = make_outside(tmp_path)
    root = tmp_path / "root"
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / "inner.txt").write_text("inner")
    real = fsread._entry_lstat

    def swap_parent(entry: Any) -> Any:
        if entry.path == str(root / "a" / "b"):
            swap_for_symlink(root / "a", outside)
        return real(entry)

    monkeypatch.setattr(fsread, "_entry_lstat", swap_parent)

    items = list(walk(root))

    assert paths(items) == [
        str(root / "a"),
        str(root / "a" / "b"),
        str(root / "a" / "b" / "inner.txt"),
    ]
    assert all(isinstance(i, WalkEntry) for i in items)


def test_list_directory_swapped_before_open_is_not_followed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside = make_outside(tmp_path)
    target = tmp_path / "listed"
    target.mkdir()
    (target / "mine.txt").write_text("mine")
    real = fsread.lstat

    def swap_after_lstat(path: Any) -> Any:
        info = real(path)
        if os.fspath(path) == str(target):
            swap_for_symlink(target, outside)
        return info

    monkeypatch.setattr(fsread, "lstat", swap_after_lstat)

    items = list_directory(target)

    assert [(i.path, i.reason) for i in items] == [(str(target), CHANGED)]


def test_list_directory_children_are_stat_relative_to_the_listed_descriptor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside = make_outside(tmp_path)
    target = tmp_path / "listed"
    (target / "b").mkdir(parents=True)
    real = fsread.lstat
    expected_ino = os.lstat(target / "b").st_ino

    def swap_on_child(path: Any) -> Any:
        if os.fspath(path) == str(target / "b"):
            swap_for_symlink(target, outside)
        return real(path)

    monkeypatch.setattr(fsread, "lstat", swap_on_child)

    (item,) = list_directory(target)

    assert isinstance(item, WalkEntry)
    assert item.path == str(target / "b")
    assert item.stat.st_ino == expected_ino


def test_regular_file_on_another_device_is_not_counted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "foreign.bin").write_text("x")
    (tmp_path / "local.bin").write_text("y")
    real = fsread._entry_lstat

    def foreign(entry: Any) -> Any:
        info = real(entry)
        if entry.path.endswith("foreign.bin"):
            return fake_stat(info, st_dev=info.st_dev + 1)
        return info

    monkeypatch.setattr(fsread, "_entry_lstat", foreign)

    items = list(walk(tmp_path))

    assert [type(i) for i in items] == [SkippedMount, WalkEntry]
    assert items[0].path == str(tmp_path / "foreign.bin")


def test_list_directory_does_not_count_a_foreign_device_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "foreign.bin").write_text("x")
    real = fsread.lstat

    def foreign(path: Any) -> Any:
        info = real(path)
        if os.fspath(path).endswith("foreign.bin"):
            return fake_stat(info, st_dev=info.st_dev + 1)
        return info

    monkeypatch.setattr(fsread, "lstat", foreign)

    assert list_directory(tmp_path) == [SkippedMount(str(tmp_path / "foreign.bin"))]


# Descriptor budget and ancestor reopening.


def build_deep(root: Path, depth: int) -> Path:
    deepest = root.joinpath(*[f"d{i}" for i in range(depth)])
    deepest.mkdir(parents=True)
    (deepest / "leaf.txt").write_text("leaf")
    for i in range(depth):
        sibling = root.joinpath(*[f"d{j}" for j in range(i)], f"z{i}")
        sibling.mkdir()
        (sibling / "s.txt").write_text("s")
    return deepest


class FdCounter:
    def __init__(self) -> None:
        self.open: set[int] = set()
        self.peak = 0
        self.directory_opens = 0
        self.real_open = os.open
        self.real_close = os.close

    def opener(self, path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        fd = self.real_open(path, flags, *args, **kwargs)
        if flags & os.O_DIRECTORY:
            self.directory_opens += 1
            self.open.add(fd)
            self.peak = max(self.peak, len(self.open))
        return fd

    def closer(self, fd: int) -> None:
        self.open.discard(fd)
        self.real_close(fd)


def test_directories_are_opened_by_descriptor_within_a_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    build_deep(tmp_path, 40)
    expected = paths(list(walk(tmp_path)))
    counter = FdCounter()
    monkeypatch.setattr(fsread, "FD_CAP", 4)
    monkeypatch.setattr(fsread.os, "open", counter.opener)
    monkeypatch.setattr(fsread.os, "close", counter.closer)

    items = list(walk(tmp_path))

    assert paths(items) == expected
    assert all(isinstance(i, WalkEntry) for i in items)
    assert counter.directory_opens >= 81
    assert counter.peak <= 4 + 2
    assert counter.open == set()


def test_reopened_ancestor_with_a_new_identity_is_not_walked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    deepest = build_deep(tmp_path, 6)
    monkeypatch.setattr(fsread, "FD_CAP", 2)
    real = fsread._entry_lstat
    d0 = tmp_path / "d0"

    def replace_d0(entry: Any) -> Any:
        info = real(entry)
        if entry.path == str(deepest / "leaf.txt"):
            os.rename(d0, tmp_path / "d0-old")
            d0.mkdir()
            (d0 / "z1").mkdir()
            (d0 / "z1" / "planted.txt").write_text("planted")
        return info

    monkeypatch.setattr(fsread, "_entry_lstat", replace_d0)

    items = list(walk(tmp_path))

    assert not any("planted" in p for p in paths(items))
    assert WalkError(str(d0), "scandir", CHANGED, None) in items


def test_early_close_releases_every_descriptor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    build_deep(tmp_path, 10)
    counter = FdCounter()
    monkeypatch.setattr(fsread.os, "open", counter.opener)
    monkeypatch.setattr(fsread.os, "close", counter.closer)

    iterator = walk(tmp_path)
    for _ in range(5):
        next(iterator)
    iterator.close()

    assert counter.open == set()


# Root-aware content opens.


def test_hash_file_beneath_reads_a_file_under_the_root(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_bytes(b"data")

    result = fsread.hash_file_beneath(tmp_path, tmp_path / "a" / "f.txt")

    assert result.bytes_read == 4


def test_hash_file_beneath_refuses_a_swapped_parent(tmp_path: Path) -> None:
    outside = make_outside(tmp_path)
    root = tmp_path / "root"
    (root / "b").mkdir(parents=True)
    (root / "b" / "secret.txt").write_text("mine")
    swap_for_symlink(root / "b", outside / "b")

    with pytest.raises(IdentityChangedError) as caught:
        fsread.hash_file_beneath(root, root / "b" / "secret.txt")

    assert caught.value.reason == CHANGED


def test_hash_file_beneath_checks_the_expected_identity(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("f")
    (tmp_path / "g.txt").write_text("g")
    other = os.lstat(tmp_path / "g.txt")

    with pytest.raises(IdentityChangedError):
        fsread.hash_file_beneath(tmp_path, tmp_path / "f.txt", expected=other)


@pytest.mark.parametrize("relative", ["../x", "a/../../x", "", "."])
def test_hash_file_beneath_refuses_paths_outside_the_root(
    tmp_path: Path, relative: str
) -> None:
    with pytest.raises(FsReadError):
        fsread.hash_file_beneath(tmp_path / "root", f"{tmp_path}/root/{relative}")


def test_hash_file_beneath_refuses_a_path_not_under_the_root(tmp_path: Path) -> None:
    with pytest.raises(FsReadError):
        fsread.hash_file_beneath(tmp_path / "root", tmp_path / "rooted" / "x")


def test_open_beneath_refuses_fifos_and_dataless_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    os.mkfifo(tmp_path / "pipe")
    (tmp_path / "cloud.txt").write_text("x")

    with pytest.raises(fsread.NotRegularFileError):
        fsread.hash_file_beneath(tmp_path, tmp_path / "pipe")
    monkeypatch.setattr(
        fsread,
        "_entry_lstat",
        lambda e: fake_stat(os.lstat(e.path), st_flags=fsread.SF_DATALESS),
    )
    with pytest.raises(fsread.DatalessFileError):
        fsread.hash_file_beneath(tmp_path, tmp_path / "cloud.txt")


def test_open_beneath_refuses_a_file_on_another_device(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "f.txt").write_text("x")
    real = fsread._entry_lstat
    monkeypatch.setattr(fsread, "_entry_lstat", lambda e: fake_stat(real(e), st_dev=-1))

    with pytest.raises(IdentityChangedError):
        fsread.hash_file_beneath(tmp_path, tmp_path / "f.txt")


def test_list_directory_of_a_symlink_is_not_followed(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "x").write_text("x")
    (tmp_path / "link").symlink_to(tmp_path / "real")

    (item,) = list_directory(tmp_path / "link")

    assert isinstance(item, WalkError)
    assert item.path == str(tmp_path / "link")
    assert item.operation == "scandir"


def test_list_directory_of_a_file_is_a_read_error(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")

    (item,) = list_directory(tmp_path / "f")

    assert item == WalkError(str(tmp_path / "f"), "scandir", "read_error", "ENOTDIR")


def test_unlistable_child_directory_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "locked").mkdir()
    real = fsread._sorted_entries

    def listing(path: Any) -> Any:
        if path == str(tmp_path / "locked"):
            raise PermissionError(13, "denied", str(path))
        return real(path)

    monkeypatch.setattr(fsread, "_sorted_entries", listing)

    items = list(walk(tmp_path))

    assert items[1] == WalkError(
        str(tmp_path / "locked"), "scandir", "permission_denied", "EACCES"
    )


def test_unlistable_root_is_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def listing(path: Any) -> Any:
        raise PermissionError(1, "not permitted", str(path))

    monkeypatch.setattr(fsread, "_sorted_entries", listing)

    assert list(walk(tmp_path)) == [
        WalkError(str(tmp_path), "scandir", "privacy_denied", "EPERM")
    ]
    assert list_directory(tmp_path) == [
        WalkError(str(tmp_path), "scandir", "privacy_denied", "EPERM")
    ]


def test_root_swapped_between_lstat_and_open_is_not_walked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside = make_outside(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    real = fsread.lstat

    def swap(path: Any) -> Any:
        info = real(path)
        if os.fspath(path) == str(root):
            swap_for_symlink(root, outside)
        return info

    monkeypatch.setattr(fsread, "lstat", swap)

    assert list(walk(root)) == [WalkError(str(root), "scandir", CHANGED, "ENOTDIR")]


def test_open_beneath_with_a_missing_root_raises_file_not_found(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError):
        fsread.hash_file_beneath(tmp_path / "gone", tmp_path / "gone" / "f")


def test_open_beneath_with_a_file_as_root_is_a_read_error(tmp_path: Path) -> None:
    (tmp_path / "root").write_text("not a directory")

    with pytest.raises(FsReadError) as caught:
        fsread.hash_file_beneath(tmp_path / "root", tmp_path / "root" / "f")

    assert not isinstance(caught.value, IdentityChangedError)


def test_open_beneath_reports_a_vanished_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        fsread.hash_file_beneath(tmp_path, tmp_path / "missing.txt")
