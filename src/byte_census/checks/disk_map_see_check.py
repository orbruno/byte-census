"""`see_check` for `disk map` findings (envelope.md, `see_check`).

Disk map emits no suggestions. A finding whose location another check covers
names that check, in this precedence: docker scan, caches scan, artifacts
scan, duplicates scan. Locations under the home folder are matched in both
spellings, the firmlinked one (`/Users/...`) and the data-volume one.

Seam: the uv, npm, and Homebrew cache locations also map to `caches scan`.
They are resolved by WI-DISK-MAP-CATEGORIES (tool caches) and passed in as
`tool_caches`; this item passes none.
"""

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from byte_census.checks.disk_map_roots import is_inside

DOCKER = "docker scan"
CACHES = "caches scan"
ARTIFACTS = "artifacts scan"
DUPLICATES = "duplicates scan"
ARTIFACT_NAMES = frozenset({"node_modules", ".venv", "venv"})
CARGO_TARGET = "target"
CARGO_MANIFEST = "Cargo.toml"
DOCKER_DATA = ("Library", "Containers", "com.docker.docker")
USER_CACHES = ("Library", "Caches")
DOWNLOADS = ("Downloads",)

Exists = Callable[[str], bool]


def _home_forms(home: str, mount: str) -> tuple[str, ...]:
    if not home:
        return ()
    if is_inside(home, mount):
        return (home,)
    return (home, mount.rstrip(os.sep) + home)


def _under_homes(homes: Iterable[str], parts: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(os.path.join(home, *parts) for home in homes)


@dataclass(frozen=True)
class SeeCheckRules:
    """Covered locations, as absolute paths, for each other check."""

    docker: tuple[str, ...]
    caches: tuple[str, ...]
    downloads: tuple[str, ...]

    @classmethod
    def for_home(
        cls, home: str, mount: str, tool_caches: Iterable[str] = ()
    ) -> "SeeCheckRules":
        homes = _home_forms(home, mount)
        return cls(
            docker=_under_homes(homes, DOCKER_DATA),
            caches=_under_homes(homes, USER_CACHES) + tuple(tool_caches),
            downloads=_under_homes(homes, DOWNLOADS),
        )

    def see_check(
        self, target: str, kind: str, exists: Exists = os.path.lexists
    ) -> str | None:
        """The check covering `target`, or None."""
        if any(is_inside(target, place) for place in self.docker):
            return DOCKER
        if any(is_inside(target, place) for place in self.caches):
            return CACHES
        if _is_artifact(target, exists):
            return ARTIFACTS
        if kind == "large_file" or target in self.downloads:
            return DUPLICATES
        return None


def _is_artifact(target: str, exists: Exists) -> bool:
    parts = target.split(os.sep)
    for index, name in enumerate(parts):
        if name in ARTIFACT_NAMES:
            return True
        if name == CARGO_TARGET and index > 0:
            manifest = os.sep.join([*parts[:index], CARGO_MANIFEST])
            if exists(manifest):
                return True
    return False
