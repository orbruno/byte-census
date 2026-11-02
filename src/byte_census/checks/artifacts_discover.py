"""Discovery of regenerable development artifacts (WI-ARTIFACTS AC-01, AC-02).

Discovery lists directories with sorted names, never follows a symlink,
never crosses `st_dev`, and does not descend into a found artifact, `.git`,
`Library`, or `.Trash`. `target` counts only beside a `Cargo.toml`.
"""

import os
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


def _has_manifest(children: list[fsread.WalkEntry]) -> bool:
    return any(
        os.path.basename(child.path) == CARGO_MANIFEST and child.kind == "file"
        for child in children
    )


def _is_artifact(name: str, has_manifest: bool) -> bool:
    if name == "target":
        return has_manifest
    return name in REGENERATE


def scan_directory(path: str, info: Any, root_dev: int) -> DirScan:
    """List one directory and sort its children into artifacts and subdirs."""
    items = fsread.list_directory(path, root_dev)
    children = [i for i in items if isinstance(i, fsread.WalkEntry)]
    has_manifest = _has_manifest(children)
    artifacts: list[Artifact] = []
    subdirs: list[tuple[str, Any]] = []
    for child in children:
        name = os.path.basename(child.path)
        if child.kind != "directory":
            continue
        if _is_artifact(name, has_manifest):
            artifacts.append(Artifact(child.path, name, path, info.st_mtime))
        elif name not in EXCLUDED:
            subdirs.append((child.path, child.stat))
    return DirScan(
        artifacts=tuple(artifacts),
        subdirs=tuple(subdirs),
        errors=tuple(i for i in items if isinstance(i, WalkError)),
        mounts=tuple(i for i in items if isinstance(i, SkippedMount)),
        visited=sum(1 for i in items if i.path != path),
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
