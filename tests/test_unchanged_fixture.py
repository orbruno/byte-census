"""Reading a tree through fsread leaves it unchanged (WI-SAFETY AC-07)."""

import os
from pathlib import Path

from byte_census.fsread import FsReadError, WalkEntry, hash_file, walk


def build_fixture(root: Path) -> None:
    (root / "docs").mkdir()
    (root / "docs" / "a.txt").write_text("alpha")
    (root / "docs" / "b.txt").write_text("alpha")
    (root / "data.bin").write_bytes(os.urandom(200_000))
    (root / "empty").write_bytes(b"")
    (root / "nested" / "deeper").mkdir(parents=True)
    (root / "nested" / "deeper" / "c.txt").write_text("gamma")
    (root / "link").symlink_to(root / "docs")
    os.mkfifo(root / "pipe")
    os.link(root / "docs" / "a.txt", root / "hardlink.txt")


def snapshot(root: Path) -> dict[str, tuple[int, int, bytes | None]]:
    """Map each path to (mode, mtime_ns, content) without following symlinks."""
    result: dict[str, tuple[int, int, bytes | None]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = os.lstat(path)
            content = (
                path.read_bytes() if path.is_file() and not path.is_symlink() else None
            )
            result[str(path)] = (info.st_mode, info.st_mtime_ns, content)
    return result


def test_hashing_and_walking_leave_contents_and_mtimes_unchanged(
    tmp_path: Path,
) -> None:
    """Hash every regular file of a fixture tree, then compare before and after.

    Contents, modes, the set of entries, and modification times must be
    identical. Access times are deliberately not compared: reading a file
    may update its access time, which is the one unavoidable side effect of
    a content read (docs/contracts/quantities.md, Limitations).
    """
    build_fixture(tmp_path)
    before = snapshot(tmp_path)
    root_mtime = os.lstat(tmp_path).st_mtime_ns

    hashed: list[str] = []
    refused: list[str] = []
    for item in walk(tmp_path):
        if not isinstance(item, WalkEntry) or item.kind == "directory":
            continue
        try:
            hash_file(item.path)
            hashed.append(os.path.basename(item.path))
        except FsReadError:
            refused.append(os.path.basename(item.path))

    assert snapshot(tmp_path) == before
    assert os.lstat(tmp_path).st_mtime_ns == root_mtime
    assert sorted(hashed) == [
        "a.txt",
        "b.txt",
        "c.txt",
        "data.bin",
        "empty",
        "hardlink.txt",
    ]
    assert sorted(refused) == ["link", "pipe"]
