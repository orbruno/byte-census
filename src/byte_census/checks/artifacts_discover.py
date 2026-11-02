"""Discovery of regenerable development artifacts (WI-ARTIFACTS AC-01, AC-02).

Discovery is one pruned `fsread.walk`: directories are listed in byte order
of names through descriptors, never by following a path string, symlinks are
never followed, `st_dev` is never crossed, and the walk does not descend into
a found artifact, `.git`, `Library`, or `.Trash`. `target` counts only beside
a `Cargo.toml` (which sorts before `target`, so it is always seen first).
Each artifact path is an `fsread.AnchoredPath`, so sizing can reach it again
beneath the scan root.
"""

import os
from dataclasses import dataclass
from typing import Any

from byte_census import fsread
from byte_census.fsread import SkippedMount, WalkEntry, WalkError, WalkItem

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
class Discovery:
    """The whole discovery pass, with artifacts in byte order of path."""

    artifacts: tuple[Artifact, ...]
    errors: tuple[WalkError, ...]
    mounts: tuple[SkippedMount, ...]
    visited: int


def _is_artifact(name: str, has_manifest: bool) -> bool:
    if name == "target":
        return has_manifest
    return name in REGENERATE


class _Discoverer:
    """Private accumulator for one discovery walk; `result` freezes it."""

    def __init__(self, root: str, root_info: Any) -> None:
        self.root = root
        self.mtimes: dict[str, float] = {root: root_info.st_mtime}
        self.manifests: set[str] = set()
        self.artifacts: list[Artifact] = []
        self.errors: list[WalkError] = []
        self.mounts: list[SkippedMount] = []
        self.visited = 0

    def prune(self, entry: WalkEntry) -> bool:
        """Record artifacts; do not descend into them or excluded folders."""
        project, name = os.path.split(entry.path)
        if _is_artifact(name, project in self.manifests):
            path = fsread.AnchoredPath(entry.path, self.root, entry.stat)
            mtime = self.mtimes[project]
            self.artifacts.append(Artifact(path, name, project, mtime))
            return True
        if name in EXCLUDED:
            return True
        self.mtimes[entry.path] = entry.stat.st_mtime
        return False

    def add(self, item: WalkItem) -> None:
        if isinstance(item, WalkEntry):
            self.visited += 1
            parent, name = os.path.split(item.path)
            if name == CARGO_MANIFEST and item.kind == "file":
                self.manifests.add(parent)
        elif isinstance(item, SkippedMount):
            self.mounts.append(item)
            self.visited += 1
        else:
            self.errors.append(item)
            self.visited += 1 if item.operation == "lstat" else 0

    def result(self) -> Discovery:
        return Discovery(
            artifacts=tuple(sorted(self.artifacts, key=_byte_order)),
            errors=tuple(self.errors),
            mounts=tuple(self.mounts),
            visited=self.visited,
        )


def _byte_order(artifact: Artifact) -> bytes:
    return os.fsencode(artifact.path)


def discover(root: str) -> Discovery:
    """Find artifacts below `root` (a resolved directory), pruned as described."""
    found = _Discoverer(root, fsread.lstat(root))
    for item in fsread.walk(root, prune=found.prune):
        found.add(item)
    return found.result()
