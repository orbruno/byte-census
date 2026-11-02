"""Discovery of regenerable development artifacts (WI-ARTIFACTS AC-01, AC-02).

Discovery lists directories with sorted names, never follows a symlink,
never crosses `st_dev`, and does not descend into a found artifact, `.git`,
`Library`, or `.Trash`. `target` counts only beside a `Cargo.toml`.
"""

import errno
import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from byte_census import fsread
from byte_census.fsread import SkippedMount, WalkError

REGENERATE: dict[str, str] = {
    "node_modules": "npm install",
    ".venv": "uv sync",
    "venv": "uv sync",
    "target": "cargo build",
}
EXCLUDED = frozenset({".git", "Library", ".Trash"})
CARGO_MANIFEST = "Cargo.toml"


@dataclass(frozen=True)
class Artifact:
    """One discovered artifact folder and the project that owns it."""

    path: str
    kind: str
    project: str
    project_mtime: float


@dataclass(frozen=True)
class DirScan:
    """What one directory listing yielded."""

    artifacts: tuple[Artifact, ...] = ()
    subdirs: tuple[tuple[str, Any], ...] = ()
    errors: tuple[WalkError, ...] = ()
    mounts: tuple[SkippedMount, ...] = ()
    visited: int = 0


@dataclass(frozen=True)
class Discovery:
    """The whole discovery pass, with artifacts in byte order of path."""

    artifacts: tuple[Artifact, ...]
    errors: tuple[WalkError, ...]
    mounts: tuple[SkippedMount, ...]
    visited: int


def _error(path: str, operation: str, error: OSError) -> WalkError:
    code = error.errno
    name = errno.errorcode.get(code) if code is not None else None
    return WalkError(path, operation, fsread.coverage_reason(code), name)


def _list(path: str, info: Any) -> tuple[list[os.DirEntry[str]], list[WalkError]]:
    if fsread.is_dataless(info):
        return [], [WalkError(path, "scandir", "dataless", None)]
    try:
        with os.scandir(path) as iterator:
            entries = sorted(iterator, key=lambda e: os.fsencode(e.name))
    except OSError as error:
        return [], [_error(path, "scandir", error)]
    return entries, []


def _stats(
    entries: list[os.DirEntry[str]],
) -> tuple[list[tuple[os.DirEntry[str], Any]], list[WalkError]]:
    pairs: list[tuple[os.DirEntry[str], Any]] = []
    errors: list[WalkError] = []
    for entry in entries:
        try:
            pairs.append((entry, entry.stat(follow_symlinks=False)))
        except OSError as error:
            errors.append(_error(entry.path, "lstat", error))
    return pairs, errors


def _has_manifest(pairs: list[tuple[os.DirEntry[str], Any]]) -> bool:
    return any(
        entry.name == CARGO_MANIFEST and stat.S_ISREG(info.st_mode)
        for entry, info in pairs
    )


def _is_artifact(name: str, has_manifest: bool) -> bool:
    if name == "target":
        return has_manifest
    return name in REGENERATE


def scan_directory(path: str, info: Any, root_dev: int) -> DirScan:
    """List one directory and sort its children into artifacts and subdirs."""
    entries, list_errors = _list(path, info)
    pairs, stat_errors = _stats(entries)
    has_manifest = _has_manifest(pairs)
    artifacts: list[Artifact] = []
    subdirs: list[tuple[str, Any]] = []
    mounts: list[SkippedMount] = []
    for entry, child in pairs:
        if not stat.S_ISDIR(child.st_mode):
            continue
        if child.st_dev != root_dev:
            mounts.append(SkippedMount(entry.path))
        elif _is_artifact(entry.name, has_manifest):
            kind = entry.name
            artifacts.append(Artifact(entry.path, kind, path, info.st_mtime))
        elif entry.name not in EXCLUDED:
            subdirs.append((entry.path, child))
    return DirScan(
        artifacts=tuple(artifacts),
        subdirs=tuple(subdirs),
        errors=tuple(list_errors + stat_errors),
        mounts=tuple(mounts),
        visited=len(entries),
    )


def _byte_order(artifact: Artifact) -> bytes:
    return os.fsencode(artifact.path)


def discover(root: str) -> Discovery:
    """Find artifacts below `root` (a resolved directory), pruned as described."""
    root_info = fsread.lstat(root)
    stack: list[tuple[str, Any]] = [(root, root_info)]
    scans = list(_drain(stack, root_info.st_dev))
    return Discovery(
        artifacts=tuple(
            sorted((a for s in scans for a in s.artifacts), key=_byte_order)
        ),
        errors=tuple(e for s in scans for e in s.errors),
        mounts=tuple(m for s in scans for m in s.mounts),
        visited=sum(s.visited for s in scans),
    )


def _drain(stack: list[tuple[str, Any]], root_dev: int) -> Iterator[DirScan]:
    while stack:
        path, info = stack.pop()
        scan = scan_directory(path, info, root_dev)
        yield scan
        stack.extend(reversed(scan.subdirs))
