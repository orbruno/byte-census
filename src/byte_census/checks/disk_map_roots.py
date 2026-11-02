"""Scan roots for `disk map`: canonical data-volume form and nesting.

Each root is validated with `paths.validate_root` (realpath once, must be a
directory), must lie on the data volume (same `st_dev` as the volume's
mount), and is reported in its data-volume form. A firmlinked path such as
`/Users/example` maps to `/System/Volumes/Data/Users/example` when that path
is the same inode. Identical roots merge (first given wins); a root inside
another root is nested: it is displayed but never walked again
(quantities.md, attribution precedence 1).
"""

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from byte_census.errors import ValidationError
from byte_census.model import ScopeRoot, order_roots
from byte_census.paths import validate_root

Lstat = Callable[[str], Any]
Validate = Callable[[str], Path]
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
    """True when path equals ancestor or lies below it."""
    return path == ancestor or path.startswith(ancestor.rstrip(os.sep) + os.sep)


def _not_on_volume(given: str, reason: str) -> ValidationError:
    return ValidationError(
        error=f"scan root is not on the data volume: {given!r}",
        reason=reason,
        suggestion=VOLUME_SUGGESTION,
    )


def _same_inode(a: Any, b: Any) -> bool:
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def _data_form(resolved: str, info: Any, volume: DataVolume, lstat: Lstat) -> str:
    """The data-volume spelling of a resolved path on the data volume."""
    if is_inside(resolved, volume.mount):
        return resolved
    candidate = volume.mount.rstrip(os.sep) + resolved
    try:
        mapped = lstat(candidate)
    except OSError:
        mapped = None
    if mapped is None or not _same_inode(mapped, info):
        raise _not_on_volume(
            resolved,
            f"{resolved} is on the data volume but {candidate} is not the same "
            "folder, so it has no data-volume form (firmlink mapping failed).",
        )
    return candidate


def canonical_root(
    given: str,
    volume: DataVolume,
    lstat: Lstat,
    validate: Validate = validate_root,
) -> ScopeRoot:
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
    return ScopeRoot(_data_form(resolved, info, volume, lstat), given, info.st_dev)


@dataclass(frozen=True)
class RootPlan:
    """Roots to walk, and for each walked root the roots nested inside it."""

    roots: tuple[ScopeRoot, ...]
    walked: tuple[str, ...]
    nested_in: tuple[tuple[str, tuple[str, ...]], ...]

    def nested(self, walked: str) -> tuple[str, ...]:
        return dict(self.nested_in).get(walked, ())

    def is_nested(self, path: str) -> bool:
        return path not in self.walked


def plan_roots(roots: Iterable[ScopeRoot]) -> RootPlan:
    """Merge identical roots and assign each nested root to its walked root.

    Roots are in ascending path order, so an enclosing root always precedes
    the roots inside it.
    """
    ordered = order_roots(roots)
    walked: list[str] = []
    nested: dict[str, list[str]] = {}
    for root in ordered:
        owner = next((w for w in walked if is_inside(root.path, w)), None)
        if owner is None:
            walked.append(root.path)
            nested[root.path] = []
        else:
            nested[owner].append(root.path)
    return RootPlan(
        roots=ordered,
        walked=tuple(walked),
        nested_in=tuple((w, tuple(nested[w])) for w in walked),
    )
