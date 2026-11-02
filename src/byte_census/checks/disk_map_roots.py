"""Scan roots for `disk map`: canonical data-volume form, identity, nesting.

Each root is validated with `paths.validate_root` (realpath once, must be a
directory), must lie on the data volume (same `st_dev` as the volume's
mount), and is reported in its data-volume form. A firmlinked path such as
`/Users/example` maps to `/System/Volumes/Data/Users/example` when that path
is the same inode. Each component is then respelled as the directory lists
it, so case or normalization variants on a case-insensitive volume share
one spelling.

Paths are only labels: identity is `(st_dev, st_ino)`. Roots with the same
identity merge (the first given wins), and nesting is decided by the
identities of each root's ancestor chain, never by comparing strings
(quantities.md, attribution precedence 1).
"""

import os
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from byte_census import fsread
from byte_census.errors import ValidationError
from byte_census.model import ScopeRoot
from byte_census.paths import validate_root

Lstat = Callable[[str], Any]
Validate = Callable[[str], Path]
ListNames = Callable[[str], list[str]]
InodeKey = tuple[int, int]
VOLUME_SUGGESTION = (
    "Pass a folder on the data volume, such as a folder under /Users or "
    "/System/Volumes/Data."
)


@dataclass(frozen=True)
class DataVolume:
    """The APFS data volume: its mount path and measured st_dev."""

    mount: str
    st_dev: int


def is_inside(path: str, ancestor: str) -> bool:
    """True when path equals ancestor or lies below it (spelling only)."""
    return path == ancestor or path.startswith(ancestor.rstrip(os.sep) + os.sep)


def identity(info: Any) -> InodeKey:
    return (info.st_dev, info.st_ino)


def list_names(path: str) -> list[str]:
    """Names in a directory, listed through fsread (never a dataless one).

    Raises OSError when the directory itself cannot be listed, as the
    callers expect; children that fail lstat still contribute their name.
    """
    # root_dev=-1 turns every child directory into a SkippedMount: only the
    # names are needed here, and nothing below the listed directory is read.
    items = fsread.list_directory(path, root_dev=-1)
    only = items[0] if len(items) == 1 else None
    if isinstance(only, fsread.WalkError) and only.path == path:
        raise OSError(f"cannot list {path}: {only.reason}")
    return [os.path.basename(item.path) for item in items]


def ancestor_chain(path: str, lstat: Lstat) -> tuple[InodeKey, ...]:
    """Identities of path and every ancestor up to `/`; unreadable ones skipped."""
    chain: list[InodeKey] = []
    current = path
    while True:
        try:
            chain.append(identity(lstat(current)))
        except OSError:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            return tuple(chain)
        current = parent


def _fold(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def _listed_name(parent: str, name: str, lstat: Lstat, names: ListNames) -> str:
    """The spelling under which `parent` lists the entry reached as `name`."""
    try:
        listed = names(parent)
        wanted = identity(lstat(os.path.join(parent, name)))
    except OSError:
        return name
    if name in listed:
        return name
    for candidate in sorted(n for n in listed if _fold(n) == _fold(name)):
        try:
            if identity(lstat(os.path.join(parent, candidate))) == wanted:
                return candidate
        except OSError:
            continue
    return name


def listed_spelling(path: str, lstat: Lstat, names: ListNames = list_names) -> str:
    """Respell every component of an absolute path as its parent lists it."""
    current = os.sep
    for part in [p for p in path.split(os.sep) if p]:
        current = os.path.join(current, _listed_name(current, part, lstat, names))
    return current


def _not_on_volume(given: str, reason: str) -> ValidationError:
    return ValidationError(
        error=f"scan root is not on the data volume: {given!r}",
        reason=reason,
        suggestion=VOLUME_SUGGESTION,
    )


def data_form(resolved: str, info: Any, volume: DataVolume, lstat: Lstat) -> str:
    """The data-volume spelling of a resolved path on the data volume."""
    if is_inside(resolved, volume.mount):
        return resolved
    candidate = volume.mount.rstrip(os.sep) + resolved
    try:
        mapped = lstat(candidate)
    except OSError:
        mapped = None
    if mapped is None or identity(mapped) != identity(info):
        raise _not_on_volume(
            resolved,
            f"{resolved} is on the data volume but {candidate} is not the same "
            "folder, so it has no data-volume form (firmlink mapping failed).",
        )
    return candidate


@dataclass(frozen=True)
class CanonicalRoot:
    """A validated root: listed data-volume spelling, argument, identity."""

    path: str
    given: str
    st_dev: int
    st_ino: int
    chain: tuple[InodeKey, ...] = ()

    @property
    def identity(self) -> InodeKey:
        return (self.st_dev, self.st_ino)

    def scope_root(self) -> ScopeRoot:
        return ScopeRoot(self.path, self.given, self.st_dev)


def canonical_root(
    given: str,
    volume: DataVolume,
    lstat: Lstat,
    validate: Validate = validate_root,
    names: ListNames = list_names,
) -> CanonicalRoot:
    """Validate one `--scan-root` and return it in data-volume form.

    Raises PathValidationError (exit 3) for an unusable path and
    ValidationError (exit 3) for a root on another volume.
    """
    resolved = str(validate(given))
    info = lstat(resolved)
    if info.st_dev != volume.st_dev:
        raise _not_on_volume(
            given,
            f"{resolved} is on device {info.st_dev}, not on the data volume "
            f"{volume.mount} (device {volume.st_dev}).",
        )
    path = listed_spelling(data_form(resolved, info, volume, lstat), lstat, names)
    chain = ancestor_chain(path, lstat)
    return CanonicalRoot(path, given, info.st_dev, info.st_ino, chain)


def merge_roots(roots: Iterable[CanonicalRoot]) -> tuple[CanonicalRoot, ...]:
    """One root per identity (first given wins), in ascending path order."""
    merged: dict[InodeKey, CanonicalRoot] = {}
    for root in roots:
        merged.setdefault(root.identity, root)
    return tuple(sorted(merged.values(), key=lambda r: r.path))
