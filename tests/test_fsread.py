"""Tests for the safe filesystem primitives (WI-SAFETY AC-04, AC-05).

Real FIFOs and symlinks are created in temporary directories. Dataless and
cross-device cases are simulated with monkeypatched stat results.
"""

import errno
import hashlib
import os
import socket
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from byte_census import fsread
from byte_census.fsread import (
    SF_DATALESS,
    DatalessFileError,
    FsReadError,
    IdentityChangedError,
    NotRegularFileError,
    SkippedMount,
    WalkEntry,
    WalkError,
    coverage_reason,
    hash_file,
    is_dataless,
    lstat,
    open_regular_file,
    walk,
)


def fake_stat(base: os.stat_result, **overrides: Any) -> SimpleNamespace:
    fields = {
        name: getattr(base, name)
        for name in dir(base)
        if name.startswith("st_") and not callable(getattr(base, name))
    }
    return SimpleNamespace(**{**fields, **overrides})


def open_and_close(path: Any) -> None:
    with open_regular_file(path):
        pass


def test_sf_dataless_value() -> None:
    assert SF_DATALESS == 0x40000000


def test_lstat_does_not_follow_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "t"
    target.write_text("x")
    link = tmp_path / "l"
    link.symlink_to(target)

    assert stat.S_ISLNK(lstat(link).st_mode)


@pytest.mark.parametrize(
    ("flags", "expected"),
    [(0, False), (SF_DATALESS, True), (SF_DATALESS | 0x1, True), (0x1, False)],
)
def test_is_dataless(flags: int, expected: bool) -> None:
    assert is_dataless(SimpleNamespace(st_flags=flags)) is expected


def test_is_dataless_without_st_flags() -> None:
    assert is_dataless(SimpleNamespace()) is False


def test_open_regular_file_reads_content(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"hello")

    with open_regular_file(path) as fd:
        assert os.read(fd, 100) == b"hello"


def test_open_uses_read_only_nofollow_nonblock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"x")
    seen: list[int] = []
    real_open = os.open

    def recording_open(target: Any, flags: int, *args: Any) -> int:
        seen.append(flags)
        return real_open(target, flags, *args)

    monkeypatch.setattr(fsread.os, "open", recording_open)
    open_and_close(path)

    assert seen == [os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK]


def test_fifo_is_refused_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)

    with pytest.raises(NotRegularFileError) as caught:
        open_and_close(fifo)

    assert caught.value.kind == "fifo"
    assert caught.value.reason == "not_regular_file"


def test_symlink_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "t"
    target.write_text("x")
    link = tmp_path / "l"
    link.symlink_to(target)

    with pytest.raises(NotRegularFileError) as caught:
        open_and_close(link)

    assert caught.value.kind == "symlink"


def test_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(NotRegularFileError) as caught:
        open_and_close(tmp_path)

    assert caught.value.kind == "directory"


def test_socket_is_refused(tmp_path: Path) -> None:
    sock_path = Path("/tmp") / f"bc-{os.getpid()}.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(sock_path))
        with pytest.raises(NotRegularFileError) as caught:
            open_and_close(sock_path)
    finally:
        server.close()
        sock_path.unlink(missing_ok=True)

    assert caught.value.kind == "socket"


def test_character_device_is_refused() -> None:
    with pytest.raises(NotRegularFileError) as caught:
        open_and_close("/dev/null")

    assert caught.value.kind == "character_device"


@pytest.mark.parametrize(
    ("mode", "kind"),
    [(stat.S_IFBLK, "block_device"), (0o170000 & 0, "unknown")],
)
def test_other_kinds_are_named(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: int, kind: str
) -> None:
    path = tmp_path / "f"
    path.write_text("x")
    monkeypatch.setattr(fsread, "lstat", lambda p: fake_stat(os.lstat(p), st_mode=mode))

    with pytest.raises(NotRegularFileError) as caught:
        open_and_close(path)

    assert caught.value.kind == kind


def test_dataless_file_is_never_opened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "cloud.txt"
    path.write_text("placeholder")
    opened: list[Any] = []
    monkeypatch.setattr(
        fsread, "lstat", lambda p: fake_stat(os.lstat(p), st_flags=SF_DATALESS)
    )
    monkeypatch.setattr(fsread.os, "open", lambda *a: opened.append(a) or -1)

    with pytest.raises(DatalessFileError) as caught:
        open_and_close(path)

    assert opened == []
    assert caught.value.reason == "dataless"
    assert caught.value.path == str(path)


def test_identity_change_between_lstat_and_open_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "a"
    path.write_text("a")
    other = tmp_path / "b"
    other.write_text("b")
    monkeypatch.setattr(fsread, "lstat", lambda p: os.lstat(other))

    with pytest.raises(IdentityChangedError) as caught:
        open_and_close(path)

    assert caught.value.reason == "changed_during_scan"


def test_fifo_swapped_in_after_lstat_is_refused_by_fstat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    real = os.lstat(fifo)
    monkeypatch.setattr(
        fsread, "lstat", lambda p: fake_stat(real, st_mode=stat.S_IFREG | 0o644)
    )

    with pytest.raises(IdentityChangedError):
        open_and_close(fifo)


def test_dataless_flag_seen_by_fstat_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "a"
    path.write_text("a")
    real_fstat = os.fstat
    monkeypatch.setattr(
        fsread.os, "fstat", lambda fd: fake_stat(real_fstat(fd), st_flags=SF_DATALESS)
    )

    with pytest.raises(DatalessFileError):
        open_and_close(path)


def test_descriptor_is_closed_after_use(tmp_path: Path) -> None:
    path = tmp_path / "a"
    path.write_text("a")

    with open_regular_file(path) as fd:
        pass

    with pytest.raises(OSError):
        os.fstat(fd)


def test_errors_share_a_base_class() -> None:
    for error_type in (NotRegularFileError, DatalessFileError, IdentityChangedError):
        assert issubclass(error_type, FsReadError)


def test_hash_file_matches_hashlib(tmp_path: Path) -> None:
    data = os.urandom(3 * 1024 * 1024 + 17)
    path = tmp_path / "big.bin"
    path.write_bytes(data)

    result = hash_file(path)

    assert result.digest == hashlib.sha256(data).hexdigest()
    assert result.bytes_read == len(data)


def test_hash_file_refuses_fifo(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)

    with pytest.raises(NotRegularFileError):
        hash_file(fifo)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (errno.EACCES, "permission_denied"),
        (errno.EPERM, "privacy_denied"),
        (errno.ENOENT, "vanished"),
        (errno.EIO, "read_error"),
        (None, "read_error"),
    ],
)
def test_coverage_reason(code: int | None, reason: str) -> None:
    assert coverage_reason(code) == reason


def build_tree(root: Path) -> None:
    (root / "b").mkdir()
    (root / "b" / "inner.txt").write_text("inner")
    (root / "a.txt").write_text("a")
    (root / "outside").mkdir()
    (root / "link_dir").symlink_to(root / "outside")
    (root / "link_file").symlink_to(root / "a.txt")
    os.mkfifo(root / "pipe")


def test_walk_never_follows_symlinks_and_orders_by_name(tmp_path: Path) -> None:
    build_tree(tmp_path)
    (tmp_path / "outside" / "hidden.txt").write_text("h")

    items = list(walk(tmp_path))
    rel = [(os.path.relpath(i.path, tmp_path), i.kind) for i in items]

    assert rel == [
        ("a.txt", "file"),
        ("b", "directory"),
        ("b/inner.txt", "file"),
        ("link_dir", "symlink"),
        ("link_file", "symlink"),
        ("outside", "directory"),
        ("outside/hidden.txt", "file"),
        ("pipe", "fifo"),
    ]
    assert all(isinstance(i, WalkEntry) for i in items)


def test_walk_entry_reports_dataless(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "cloud").write_text("x")
    real = fsread._entry_lstat
    monkeypatch.setattr(
        fsread, "_entry_lstat", lambda e: fake_stat(real(e), st_flags=SF_DATALESS)
    )

    (entry,) = list(walk(tmp_path))

    assert isinstance(entry, WalkEntry)
    assert entry.is_dataless is True


def test_walk_does_not_descend_across_device(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "mnt").mkdir()
    (tmp_path / "mnt" / "other.txt").write_text("o")
    (tmp_path / "z.txt").write_text("z")
    real = fsread._entry_lstat

    def entry_lstat(entry: os.DirEntry[str]) -> Any:
        result = real(entry)
        if entry.name == "mnt":
            return fake_stat(result, st_dev=result.st_dev + 1)
        return result

    monkeypatch.setattr(fsread, "_entry_lstat", entry_lstat)

    items = list(walk(tmp_path))

    assert [type(i) for i in items] == [SkippedMount, WalkEntry]
    assert items[0].path == str(tmp_path / "mnt")
    assert items[1].path == str(tmp_path / "z.txt")


def test_walk_reports_scandir_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "locked").mkdir()
    real_scandir = os.scandir

    def scandir(path: Any) -> Any:
        if os.fspath(path).endswith("locked"):
            raise PermissionError(errno.EPERM, "Operation not permitted", path)
        return real_scandir(path)

    monkeypatch.setattr(fsread.os, "scandir", scandir)

    items = list(walk(tmp_path))

    assert isinstance(items[1], WalkError)
    assert items[1].operation == "scandir"
    assert items[1].reason == "privacy_denied"
    assert items[1].errno_name == "EPERM"


def test_walk_reports_vanished_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "gone").write_text("x")

    def vanish(entry: os.DirEntry[str]) -> Any:
        raise FileNotFoundError(errno.ENOENT, "No such file", entry.path)

    monkeypatch.setattr(fsread, "_entry_lstat", vanish)

    (item,) = list(walk(tmp_path))

    assert isinstance(item, WalkError)
    assert item.operation == "lstat"
    assert item.reason == "vanished"


def test_walk_rejects_non_directory_root(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_text("x")

    with pytest.raises(NotADirectoryError):
        list(walk(path))


def test_walk_items_are_immutable(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")

    (entry,) = list(walk(tmp_path))

    with pytest.raises(AttributeError):
        entry.path = "/"  # type: ignore[misc]
