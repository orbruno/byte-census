"""Managed categories and tool caches for `disk map` (parity matrix S19, S24, S25).

The ten categories keep the labels and catalog order of storage-inventory.sh.
Their paths are built from the injected home folder and data-volume mount, so
tests never touch the real home. Tool cache locations reuse the WI-CACHES
resolution (`uv cache dir`, `brew --cache`, npm from configuration only).

A location that does not exist, or is not a real directory, is omitted. One
on another device is a skipped mount. One that cannot be examined becomes an
`incomplete_coverage` entry. Two tool caches at one location are one scope:
the first tool in the order uv, npm, brew keeps it.
"""

import errno
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from byte_census.checks.disk_map_roots import (
    DataVolume,
    Lstat,
    ancestor_chain,
    data_form,
    identity,
    is_inside,
    listed_spelling,
)
from byte_census.checks.disk_map_scopes import CATEGORY, TOOL_CACHE, DeclaredScope
from byte_census.checks.tool_caches import ToolRunner, resolve_tool_caches
from byte_census.errors import ValidationError
from byte_census.fsread import coverage_reason
from byte_census.model import CoverageEntry, UnavailableSource

HOME_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User caches", ("Library", "Caches")),
    ("Application support", ("Library", "Application Support")),
    ("App containers", ("Library", "Containers")),
    ("Group containers", ("Library", "Group Containers")),
    ("Developer data", ("Library", "Developer")),
    (
        "Device backups (inside Application support)",
        ("Library", "Application Support", "MobileSync", "Backup"),
    ),
    ("Mail", ("Library", "Mail")),
    ("Messages", ("Library", "Messages")),
    ("Downloads", ("Downloads",)),
)
APPLICATIONS = ("Applications", "Applications")


@dataclass(frozen=True)
class CategorySpec:
    """One catalog entry: its label and absolute path."""

    label: str
    path: str


def home_data_form(home: str, mount: str) -> str:
    """The home folder spelled on the data volume (firmlink form)."""
    if not home or is_inside(home, mount):
        return home
    return mount.rstrip(os.sep) + home


def default_categories(home: str, mount: str) -> tuple[CategorySpec, ...]:
    """The ten categories in catalog order; home ones only with a home."""
    base = home_data_form(home, mount)
    found = [
        CategorySpec(label, os.path.join(base, *parts))
        for label, parts in HOME_CATEGORIES
        if base
    ]
    label, name = APPLICATIONS
    return (*found, CategorySpec(label, os.path.join(mount, name)))


@dataclass(frozen=True)
class Located:
    """Scopes found, and what could not be used, for one resolution step."""

    scopes: tuple[DeclaredScope, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    mounts: tuple[str, ...] = ()
    unavailable: tuple[UnavailableSource, ...] = ()
    stdout_sizes: tuple[int, ...] = ()


Locate = Callable[[str], DeclaredScope | CoverageEntry | str | None]


def _locator(volume: DataVolume, lstat: Lstat, kind: str, **labels: Any) -> Locate:
    def locate(path: str) -> DeclaredScope | CoverageEntry | str | None:
        try:
            info = lstat(path)
        except FileNotFoundError:
            return None
        except OSError as error:
            name = errno.errorcode.get(error.errno) if error.errno else None
            return CoverageEntry(path, coverage_reason(error.errno), name, "lstat")
        if not stat.S_ISDIR(info.st_mode):
            return None
        if info.st_dev != volume.st_dev:
            return path
        try:
            spelled = listed_spelling(data_form(path, info, volume, lstat), lstat)
        except ValidationError:
            return None
        chain = ancestor_chain(spelled, lstat)
        return DeclaredScope(kind, spelled, identity(info), chain, **labels)

    return locate


def _merge_tool(first: DeclaredScope, later: DeclaredScope) -> DeclaredScope:
    """Keep one scope per location; a later tool there is recorded, not counted.

    Location uncertainty of every tool at the location is kept, in tool order.
    """
    if later.kind != TOOL_CACHE:
        return first
    other = (later.tool, later.location_source)
    notes = [note for note in (first.uncertain, later.uncertain) if note]
    return replace(
        first,
        other_tools=(*first.other_tools, other),
        uncertain="; ".join(notes) if notes else None,
    )


def _collect(outcomes: Sequence[DeclaredScope | CoverageEntry | str | None]) -> Located:
    scopes: list[DeclaredScope] = []
    for outcome in outcomes:
        if not isinstance(outcome, DeclaredScope):
            continue
        same = [i for i, s in enumerate(scopes) if s.identity == outcome.identity]
        if same:
            scopes[same[0]] = _merge_tool(scopes[same[0]], outcome)
        else:
            scopes.append(outcome)
    return Located(
        scopes=tuple(scopes),
        coverage=tuple(o for o in outcomes if isinstance(o, CoverageEntry)),
        mounts=tuple(o for o in outcomes if isinstance(o, str)),
    )


def locate_categories(
    categories: Sequence[CategorySpec], volume: DataVolume, lstat: Lstat
) -> Located:
    """Category scopes in catalog order."""
    return _collect(
        [_locator(volume, lstat, CATEGORY, label=c.label)(c.path) for c in categories]
    )


def locate_tool_caches(
    environ: Mapping[str, str], run: ToolRunner, volume: DataVolume, lstat: Lstat
) -> Located:
    """uv, npm, and brew cache scopes, each location once under the first
    tool; later tools at that location are kept in `other_tools`."""
    tools = resolve_tool_caches(environ, run)
    found = _collect(
        [
            _locator(
                volume,
                lstat,
                TOOL_CACHE,
                tool=cache.tool,
                location_source=cache.location_source,
                uncertain=cache.uncertain,
            )(cache.path)
            for cache in tools.caches
        ]
    )
    return Located(
        scopes=found.scopes,
        coverage=found.coverage + tools.coverage,
        mounts=found.mounts,
        unavailable=tools.unavailable,
        stdout_sizes=tools.stdout_sizes,
    )
