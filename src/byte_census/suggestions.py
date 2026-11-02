"""Cleanup suggestion catalog (docs/contracts/envelope.md, Suggestion).

Suggestions are text only. This module builds `model.Suggestion` objects from
catalog templates and never runs, imports a runner for, or hands a command to
anything: no suggestion string reaches the runner (WI-SUGGESTIONS AC-04).
"""

import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from byte_census.model import RISKS, FrozenMap, Suggestion, order_suggestions

__all__ = [
    "CATALOG",
    "SuggestionTemplate",
    "build_artifact_suggestion",
    "build_check_wide",
    "build_duplicate_suggestion",
    "order_suggestions",
]

CHECK_WIDE = "check-wide"
PER_FINDING = "per-finding"


@dataclass(frozen=True)
class SuggestionTemplate:
    """One catalog entry. `command` and `reason` may hold `{operand}` slots."""

    id: str
    command: str
    risk: str
    reversible: bool
    reason: str
    scope: str

    def __post_init__(self) -> None:
        if self.risk not in RISKS:
            raise ValueError(f"unknown risk: {self.risk!r}")
        if self.scope not in (CHECK_WIDE, PER_FINDING):
            raise ValueError(f"unknown scope: {self.scope!r}")


def _wide(id_: str, command: str, risk: str, reason: str) -> SuggestionTemplate:
    return SuggestionTemplate(id_, command, risk, False, reason, CHECK_WIDE)


_ENTRIES = (
    _wide(
        "docker-image-prune",
        "docker image prune",
        "low",
        "Removes dangling images only; Docker reports them as reclaimable.",
    ),
    _wide(
        "docker-container-prune",
        "docker container prune",
        "medium",
        "Removes all stopped containers and their writable layers.",
    ),
    _wide(
        "docker-system-prune-all",
        "docker system prune -a",
        "high",
        "Removes every unused image, stopped container, network, and build cache "
        "entry; volumes are kept because the command has no --volumes.",
    ),
    _wide(
        "docker-volume-prune",
        "docker volume prune",
        "high",
        "Removes unused volumes, which can hold the only copy of application data.",
    ),
    _wide(
        "uv-cache-prune",
        "uv cache prune",
        "low",
        "Removes unused entries from the uv cache; uv downloads them again when "
        "needed.",
    ),
    _wide(
        "brew-cleanup",
        "brew cleanup",
        "low",
        "Removes outdated downloads and old formula versions from the Homebrew cache.",
    ),
    _wide(
        "npm-cache-verify",
        "npm cache verify",
        "low",
        "Verifies the npm cache and removes corrupted and unreferenced entries.",
    ),
    SuggestionTemplate(
        "artifact-remove-regenerate",
        "rm -rf -- {artifact} && cd -- {project} && {regenerate}",
        "medium",
        False,
        "{name} is regenerable with `{regenerate}`; removal frees at most its "
        "allocated size.",
        PER_FINDING,
    ),
    SuggestionTemplate(
        "duplicate-remove-extra-copies",
        "rm -- {path}",
        "high",
        False,
        "Identical content. The command keeps {keep} only because it sorts "
        "first; the owner chooses which copy to keep. Every name of a removed "
        "copy is listed, because removing one hard-link name frees nothing.",
        PER_FINDING,
    ),
)

CATALOG: Mapping[str, SuggestionTemplate] = FrozenMap(
    tuple((entry.id, entry) for entry in _ENTRIES)
)


_ESCAPES = {"\\": "\\\\", "'": "\\'", "\n": "\\n", "\t": "\\t", "\r": "\\r"}

# Fixed regeneration command per artifact directory name (WI-ARTIFACTS).
REGENERATE: Mapping[str, str] = FrozenMap(
    (
        ("node_modules", "npm install"),
        (".venv", "uv sync"),
        ("venv", "uv sync"),
        ("target", "cargo build"),
    )
)


def _has_control(value: str) -> bool:
    return any(unicodedata.category(ch) == "Cc" for ch in value)


def _ansi_c_char(ch: str) -> str:
    if ch in _ESCAPES:
        return _ESCAPES[ch]
    if unicodedata.category(ch) == "Cc":
        return f"\\x{ord(ch):02x}"
    return ch


def quote(value: str) -> str:
    """Quote a shell operand: plain single quotes, or `$'...'` ANSI-C quoting
    when the value holds a control character, so no raw control character
    appears in the output."""
    if _has_control(value):
        return "$'" + "".join(_ansi_c_char(ch) for ch in value) + "'"
    return "'" + value.replace("'", "'\\''") + "'"


def _template(catalog_id: str, scope: str) -> SuggestionTemplate:
    template = CATALOG[catalog_id]
    if template.scope != scope:
        raise ValueError(f"{catalog_id} is {template.scope}, not {scope}")
    return template


def _make(
    template: SuggestionTemplate,
    id_: str,
    command: str,
    reason: str,
    finding_ids: Iterable[str],
) -> Suggestion:
    return Suggestion(
        id=id_,
        command=command,
        risk=template.risk,
        reversible=template.reversible,
        reason=reason,
        finding_ids=tuple(finding_ids),
    )


def build_check_wide(catalog_id: str, finding_ids: Iterable[str]) -> Suggestion:
    """A check-wide suggestion relating all `finding_ids`, in the given order."""
    template = _template(catalog_id, CHECK_WIDE)
    ids = tuple(finding_ids)
    if not ids:
        raise ValueError("a check-wide suggestion needs at least one related finding")
    return _make(template, template.id, template.command, template.reason, ids)


def build_artifact_suggestion(
    finding_id: str, artifact_path: str, project_path: str, regenerate: str
) -> Suggestion:
    """Remove one artifact, then regenerate it from its project directory."""
    template = _template("artifact-remove-regenerate", PER_FINDING)
    name = PurePosixPath(artifact_path).name
    if REGENERATE.get(name) != regenerate:
        raise ValueError(
            f"regenerate must be {REGENERATE.get(name)!r} for {name!r}, "
            f"got {regenerate!r}"
        )
    command = template.command.format(
        artifact=quote(artifact_path),
        project=quote(project_path),
        regenerate=regenerate,
    )
    reason = template.reason.format(
        name=quote(name) if _has_control(name) else name, regenerate=regenerate
    )
    return _make(
        template, f"{template.id}@{finding_id}", command, reason, (finding_id,)
    )


def build_duplicate_suggestion(
    finding_id: str, keep_path: str, remove_paths: Sequence[str]
) -> Suggestion:
    """Remove every listed name of every copy except the one kept."""
    template = _template("duplicate-remove-extra-copies", PER_FINDING)
    if not remove_paths:
        raise ValueError("a duplicate suggestion needs at least one path to remove")
    if keep_path in remove_paths:
        raise ValueError(f"the kept path is also listed for removal: {keep_path!r}")
    command = " && ".join(template.command.format(path=quote(p)) for p in remove_paths)
    reason = template.reason.format(keep=quote(keep_path))
    return _make(
        template, f"{template.id}@{finding_id}", command, reason, (finding_id,)
    )
