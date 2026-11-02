"""Residual path-following walkers (closure check of security MEDIUM 1).

Each proof of concept swaps a directory below the scan root for a symlink to
an outside tree at a deterministic point: after the walker has examined an
entry and before it lists or measures that entry.
"""

import copy
import os
import pickle
from pathlib import Path
from typing import Any

import pytest

from byte_census import fsread
from byte_census.checks import artifacts_discover, artifacts_size, disk_map_walk
from byte_census.fsread import SkippedMount, WalkEntry, WalkError

CHANGED = "changed_during_scan"


def pickle_round_trip(value: Any) -> Any:
    return pickle.loads(pickle.dumps(value))


SECRET = "SECRET_OUTSIDE"


def make_outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    for sub in ("b", "node_modules"):
        (outside / sub).mkdir(parents=True)
        (outside / sub / SECRET).write_bytes(b"s" * 5000)
    return outside


def swap_for_symlink(directory: Path, target: Path) -> None:
    os.rename(directory, directory.with_name(directory.name + "-moved"))
    os.symlink(target, directory)


class SwapOnce:
    """Swap `directory` for a symlink the first time `trigger` is examined."""

    def __init__(self, directory: Path, target: Path, trigger: Path) -> None:
        self.directory = directory
        self.target = target
        self.trigger = str(trigger)
        self.done = False

    def fire(self, path: Any) -> None:
        if not self.done and os.fspath(path) == self.trigger:
            self.done = True
            swap_for_symlink(self.directory, self.target)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Hook both stat seams, so the swap fires in old and new walkers."""
        real_lstat = fsread.lstat
        real_entry = fsread._entry_lstat

        def lstat(path: Any) -> Any:
            info = real_lstat(path)
            self.fire(path)
            return info

        def entry_lstat(entry: Any) -> Any:
            info = real_entry(entry)
            self.fire(entry.path)
            return info

        monkeypatch.setattr(fsread, "lstat", lstat)
        monkeypatch.setattr(fsread, "_entry_lstat", entry_lstat)


def paths(items: Any) -> list[str]:
    return [item.path for item in items]


# Proof of concept 1: disk map's pruned walk.


def test_poc_disk_map_pruned_walk_stays_below_the_root(tmp_path: Path) -> None:
    outside = make_outside(tmp_path)
    root = tmp_path / "root"
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / "mine.txt").write_text("mine")
    swapped: list[str] = []

    def prune(entry: WalkEntry) -> bool:
        if entry.path == str(root / "a" / "b") and not swapped:
            swapped.append(entry.path)
            swap_for_symlink(root / "a", outside)
        return False

    info = os.lstat(root)
    items = list(disk_map_walk.walk_pruned(str(root), info.st_dev, prune))

    assert swapped
    assert not any(SECRET in p for p in paths(items))
    assert str(root / "a" / "b" / "mine.txt") in paths(items)


def test_disk_map_pruned_directories_vanish(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "k.txt").write_text("k")
    (tmp_path / "skip").mkdir()
    (tmp_path / "skip" / "s.txt").write_text("s")

    def prune(entry: WalkEntry) -> bool:
        return entry.path.endswith("skip")

    info = os.lstat(tmp_path)
    items = list(disk_map_walk.walk_pruned(str(tmp_path), info.st_dev, prune))

    assert paths(items) == [str(tmp_path / "keep"), str(tmp_path / "keep" / "k.txt")]


# Proof of concept 2: artifacts discovery.


def test_poc_artifacts_discovery_stays_below_the_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    outside = make_outside(tmp_path)
    (outside / "b" / "node_modules").mkdir()
    root = tmp_path / "root"
    (root / "a" / "b").mkdir(parents=True)
    swap = SwapOnce(root / "a", outside, root / "a" / "b")
    swap.install(monkeypatch)

    found = artifacts_discover.discover(str(root))

    assert swap.done
    assert found.artifacts == ()
    assert not any(SECRET in e.path for e in found.errors)


def test_discovery_finds_artifacts_and_respects_cargo_and_exclusions(
    tmp_path: Path,
) -> None:
    (tmp_path / "web" / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "rust" / "target").mkdir(parents=True)
    (tmp_path / "rust" / "Cargo.toml").write_text("[package]")
    (tmp_path / "plain" / "target").mkdir(parents=True)
    (tmp_path / ".git" / "node_modules").mkdir(parents=True)
    (tmp_path / "py" / ".venv").mkdir(parents=True)

    found = artifacts_discover.discover(str(tmp_path))

    assert [(a.path, a.kind, a.project) for a in found.artifacts] == [
        (str(tmp_path / "py" / ".venv"), ".venv", str(tmp_path / "py")),
        (str(tmp_path / "rust" / "target"), "target", str(tmp_path / "rust")),
        (str(tmp_path / "web" / "node_modules"), "node_modules", str(tmp_path / "web")),
    ]
    web = os.lstat(tmp_path / "web")
    assert found.artifacts[2].project_mtime == web.st_mtime
    assert found.visited == 10


def test_discovery_records_dataless_and_foreign_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "cloud").mkdir()
    (tmp_path / "mnt").mkdir()
    real = fsread._entry_lstat

    def entry_lstat(entry: Any) -> Any:
        info = real(entry)
        fields = {n: getattr(info, n) for n in dir(info) if n.startswith("st_")}
        if entry.path.endswith("cloud"):
            fields["st_flags"] = fsread.SF_DATALESS
        if entry.path.endswith("mnt"):
            fields["st_dev"] = info.st_dev + 1
        return type("Info", (), fields)()

    monkeypatch.setattr(fsread, "_entry_lstat", entry_lstat)

    found = artifacts_discover.discover(str(tmp_path))

    assert found.errors == (
        WalkError(str(tmp_path / "cloud"), "scandir", "dataless", None),
    )
    assert found.mounts == (SkippedMount(str(tmp_path / "mnt")),)


# Proof of concept 3: artifact sizing after discovery.


def test_poc_artifact_sizing_after_a_parent_swap_counts_nothing_outside(
    tmp_path: Path,
) -> None:
    outside = make_outside(tmp_path)
    root = tmp_path / "root"
    (root / "proj" / "node_modules").mkdir(parents=True)
    (root / "proj" / "node_modules" / "dep.js").write_bytes(b"d" * 100)
    (artifact,) = artifacts_discover.discover(str(root)).artifacts
    swap_for_symlink(root / "proj", outside)

    measure = artifacts_size.measure_subtree(
        artifact.path, frozenset(), root=str(root), expected=artifact.path.expected
    )

    assert measure.logical_bytes == 0
    assert [(e.path, e.reason) for e in measure.errors] == [
        (str(root / "proj" / "node_modules"), CHANGED)
    ]


def test_artifact_sizing_of_a_normal_tree_is_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "proj" / "node_modules" / "pkg").mkdir(parents=True)
    (root / "proj" / "node_modules" / "pkg" / "a.js").write_bytes(b"a" * 300)
    (root / "proj" / "node_modules" / "b.js").write_bytes(b"b" * 200)
    (artifact,) = artifacts_discover.discover(str(root)).artifacts

    measure = artifacts_size.measure_subtree(
        artifact.path, frozenset(), root=str(root), expected=artifact.path.expected
    )

    assert measure.logical_bytes == 500
    assert measure.visited == 3
    assert measure.errors == ()


def test_stripped_anchor_still_measures_beneath_the_root(tmp_path: Path) -> None:
    """Proof of concept: a stripped anchor used to fall back to a path walk."""
    outside = make_outside(tmp_path)
    root = tmp_path / "root"
    (root / "proj" / "node_modules").mkdir(parents=True)
    (artifact,) = artifacts_discover.discover(str(root)).artifacts
    expected = artifact.path.expected
    stripped = f"{artifact.path}"
    swap_for_symlink(root / "proj", outside)

    measure = artifacts_size.measure_subtree(
        stripped, frozenset(), root=str(root), expected=expected
    )

    assert measure.logical_bytes == 0
    assert [e.reason for e in measure.errors] == [CHANGED]


def test_sizing_without_a_root_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "p" / ".venv").mkdir(parents=True)

    with pytest.raises(TypeError):
        artifacts_size.measure_subtree(  # type: ignore[call-arg]
            str(tmp_path / "p" / ".venv"), frozenset()
        )


def test_artifact_check_refuses_an_artifact_without_its_discovery_anchor(
    tmp_path: Path,
) -> None:
    from byte_census.checks import artifacts

    (tmp_path / "p" / ".venv").mkdir(parents=True)
    plain = artifacts_discover.Artifact(
        str(tmp_path / "p" / ".venv"), ".venv", str(tmp_path / "p"), 0.0
    )

    with pytest.raises(TypeError, match="anchor"):
        artifacts._measure_all((plain,), str(tmp_path))


@pytest.mark.parametrize("duplicate", [copy.copy, copy.deepcopy, pickle_round_trip])
def test_anchored_path_survives_copy_and_pickle(tmp_path: Path, duplicate: Any) -> None:
    info = os.lstat(tmp_path)
    anchored = fsread.AnchoredPath(str(tmp_path / "x"), str(tmp_path), info)

    clone = duplicate(anchored)

    assert isinstance(clone, fsread.AnchoredPath)
    assert clone == anchored
    assert clone.root == str(tmp_path)
    assert (clone.expected.st_dev, clone.expected.st_ino) == (info.st_dev, info.st_ino)


def test_artifact_path_is_an_ordinary_string_for_output(tmp_path: Path) -> None:
    (tmp_path / "p" / ".venv").mkdir(parents=True)
    (artifact,) = artifacts_discover.discover(str(tmp_path)).artifacts

    assert artifact.path == str(tmp_path / "p" / ".venv")
    assert str(artifact.path) == artifact.path
    assert repr(artifact.path) == repr(str(tmp_path / "p" / ".venv"))


# fsread: pruning and resuming below a known directory.


def test_walk_prune_keeps_the_entry_but_does_not_descend(tmp_path: Path) -> None:
    (tmp_path / "a" / "deep").mkdir(parents=True)
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "f").write_text("f")
    seen: list[str] = []

    def prune(entry: WalkEntry) -> bool:
        seen.append(entry.path)
        return entry.path.endswith("/a")

    items = list(fsread.walk(tmp_path, prune=prune))

    assert paths(items) == [
        str(tmp_path / "a"),
        str(tmp_path / "b"),
        str(tmp_path / "b" / "f"),
    ]
    assert seen == [str(tmp_path / "a"), str(tmp_path / "b")]


def test_walk_beneath_yields_the_start_then_its_subtree(tmp_path: Path) -> None:
    (tmp_path / "x" / "y").mkdir(parents=True)
    (tmp_path / "x" / "y" / "f").write_text("f")
    expected = os.lstat(tmp_path / "x")

    items = list(fsread.walk_beneath(tmp_path, tmp_path / "x", expected))

    assert paths(items) == [
        str(tmp_path / "x"),
        str(tmp_path / "x" / "y"),
        str(tmp_path / "x" / "y" / "f"),
    ]
    assert items[0].stat.st_ino == expected.st_ino


def test_walk_beneath_refuses_an_identity_mismatch(tmp_path: Path) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()

    items = list(
        fsread.walk_beneath(tmp_path, tmp_path / "x", os.lstat(tmp_path / "y"))
    )

    assert items == [WalkError(str(tmp_path / "x"), "scandir", CHANGED, None)]


def test_walk_beneath_uses_the_root_device(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "f").write_text("f")
    expected = os.lstat(tmp_path / "x")
    real = fsread._entry_lstat

    def foreign(entry: Any) -> Any:
        info = real(entry)
        fields = {n: getattr(info, n) for n in dir(info) if n.startswith("st_")}
        return type("Info", (), {**fields, "st_dev": info.st_dev + 1})()

    monkeypatch.setattr(fsread, "_entry_lstat", foreign)

    items = list(fsread.walk_beneath(tmp_path, tmp_path / "x", expected))

    assert items[1:] == [SkippedMount(str(tmp_path / "x" / "f"))]


def test_walk_beneath_of_a_vanished_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        list(fsread.walk_beneath(tmp_path, tmp_path / "gone", os.lstat(tmp_path)))


def test_walk_beneath_of_a_dataless_start_is_not_listed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "f").write_text("f")
    expected = os.lstat(tmp_path / "x")
    real_fstat = os.fstat

    def dataless(fd: int) -> Any:
        info = real_fstat(fd)
        fields = {n: getattr(info, n) for n in dir(info) if n.startswith("st_")}
        if fields["st_ino"] == expected.st_ino:
            fields["st_flags"] = fsread.SF_DATALESS
        return type("Info", (), fields)()

    monkeypatch.setattr(fsread.os, "fstat", dataless)

    items = list(fsread.walk_beneath(tmp_path, tmp_path / "x", expected))

    assert [type(i) for i in items] == [WalkEntry, WalkError]
    assert items[1].reason == "dataless"


# LOW: a failing fstat after opening a file must not leak the descriptor.


def test_open_beneath_closes_the_file_when_fstat_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "f").write_text("f")
    opened: list[int] = []
    closed: list[int] = []
    real_open, real_close, real_fstat = os.open, os.close, os.fstat

    def opener(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        fd = real_open(path, flags, *args, **kwargs)
        if not flags & os.O_DIRECTORY:
            opened.append(fd)
        return fd

    def closer(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    def fstat(fd: int) -> Any:
        if fd in opened:
            raise OSError(5, "Input/output error")
        return real_fstat(fd)

    monkeypatch.setattr(fsread.os, "open", opener)
    monkeypatch.setattr(fsread.os, "close", closer)
    monkeypatch.setattr(fsread.os, "fstat", fstat)

    with pytest.raises(OSError):
        fsread.hash_file_beneath(tmp_path, tmp_path / "f")

    assert opened and set(opened) <= set(closed)


def test_disk_map_pruned_walk_of_an_empty_root_yields_nothing(tmp_path: Path) -> None:
    info = os.lstat(tmp_path)

    assert list(disk_map_walk.walk_pruned(str(tmp_path), info.st_dev, bool)) == []


def test_disk_map_pruned_walk_of_a_file_root_reports_one_error(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_text("f")
    info = os.lstat(path)

    items = list(disk_map_walk.walk_pruned(str(path), info.st_dev, bool))

    assert items == [WalkError(str(path), "scandir", "read_error", "ENOTDIR")]
