"""Immutable observation model and its serialization (docs/contracts/envelope.md).

Every check reports through these frozen dataclasses. `to_dict` returns plain
dicts and lists with the exact field names and field order of the contract
examples. Mapping fields (`details`, `summary`, `options`, `extra`, `notes`)
are frozen on construction, so a model object cannot change after creation.
"""

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

from byte_census import __version__

SCHEMA_VERSION = "1.0.0"
TOOL_NAME = "byte-census"

# Finding ID prefixes from envelope.md; `tst` is internal to `_selftest`.
ID_PREFIXES = frozenset({"dkr", "cch", "art", "dup", "map", "tst"})
RISKS = ("low", "medium", "high")
EXIT_CODES: Mapping[str, int] = MappingProxyType(
    {
        "internal_error": 1,
        "usage_error": 2,
        "validation_error": 3,
        "source_unavailable": 4,
    }
)
PARTIAL_SOURCE_REASONS = frozenset({"failed", "timed_out"})
COST_NULLABLE = (
    "content_bytes_read",
    "entries_visited",
    "subprocess_calls",
    "subprocess_stdout_bytes",
    "subprocess_content_bytes_read",
)

EMPTY: Mapping[str, Any] = MappingProxyType({})


def freeze(value: Any) -> Any:
    """Return a read-only deep copy: mappings become proxies, lists tuples."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value: Any) -> Any:
    """Return plain JSON types: mappings become dicts, tuples lists."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


def _freeze_fields(obj: Any, *names: str) -> None:
    for name in names:
        object.__setattr__(obj, name, freeze(getattr(obj, name)))


def finding_id(prefix: str, kind: str, target: str) -> str:
    """`<prefix>-<first 12 hex of SHA-256 of "<kind>\\0<target>">`."""
    if prefix not in ID_PREFIXES:
        raise ValueError(f"unknown finding ID prefix: {prefix!r}")
    digest = hashlib.sha256(f"{kind}\0{target}".encode()).hexdigest()
    return f"{prefix}-{digest[:12]}"


def format_captured_at(moment: datetime) -> str:
    """RFC 3339 in UTC with `Z`, at second precision."""
    if moment.tzinfo is None:
        raise ValueError("captured_at needs a timezone-aware datetime")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Classification:
    """Record-vocabulary fields; byte-census observes, it does not classify."""

    owner: str = ""
    status: str = "unknown"
    recovery: str = "unknown"
    confidence: str = "low"
    disposition: str = "investigate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "status": self.status,
            "recovery": self.recovery,
            "confidence": self.confidence,
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class Finding:
    """One observation; the shape is fixed from schema 1.0.0 (AC-02)."""

    id: str
    kind: str
    target: str
    logical_bytes: int | None = None
    allocated_bytes: int | None = None
    reclaimable_estimate_bytes: int | None = None
    caveats: tuple[str, ...] = ()
    see_check: str | None = None
    suggestion_ids: tuple[str, ...] = ()
    classification: Classification = field(default_factory=Classification)
    details: Mapping[str, Any] = EMPTY

    def __post_init__(self) -> None:
        _freeze_fields(self, "caveats", "suggestion_ids", "details")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "target": self.target,
            "logical_bytes": self.logical_bytes,
            "allocated_bytes": self.allocated_bytes,
            "reclaimable_estimate_bytes": self.reclaimable_estimate_bytes,
            "caveats": list(self.caveats),
            "see_check": self.see_check,
            "suggestion_ids": list(self.suggestion_ids),
            "classification": self.classification.to_dict(),
            "details": thaw(self.details),
        }


@dataclass(frozen=True)
class Suggestion:
    """Text-only cleanup suggestion; never executed."""

    id: str
    command: str
    risk: str
    reversible: bool
    reason: str
    finding_ids: tuple[str, ...] = ()
    requires_owner_authorization: bool = True

    def __post_init__(self) -> None:
        if self.risk not in RISKS:
            raise ValueError(f"unknown risk: {self.risk!r}")
        if self.requires_owner_authorization is not True:
            raise ValueError("requires_owner_authorization is always true")
        _freeze_fields(self, "finding_ids")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "risk": self.risk,
            "reversible": self.reversible,
            "requires_owner_authorization": self.requires_owner_authorization,
            "reason": self.reason,
            "finding_ids": list(self.finding_ids),
        }


@dataclass(frozen=True)
class CoverageEntry:
    """One path the check could not observe (quantities.md)."""

    path: str
    reason: str
    errno: str | None
    operation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reason": self.reason,
            "errno": self.errno,
            "operation": self.operation,
        }


@dataclass(frozen=True)
class UnavailableSource:
    """An optional source that could not be used."""

    source: str
    reason: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "reason": self.reason, "detail": self.detail}


@dataclass(frozen=True)
class ScopeRoot:
    """A scan root: resolved path, the argument as given, and measured st_dev."""

    path: str
    given: str
    st_dev: int

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "given": self.given, "st_dev": self.st_dev}


@dataclass(frozen=True)
class Scope:
    """Roots, effective options, and mounts where descent stopped."""

    roots: tuple[ScopeRoot, ...] = ()
    options: Mapping[str, Any] = EMPTY
    skipped_mounts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _freeze_fields(self, "roots", "options", "skipped_mounts")

    def to_dict(self) -> dict[str, Any]:
        return {
            "roots": [root.to_dict() for root in self.roots],
            "options": thaw(self.options),
            "skipped_mounts": list(self.skipped_mounts),
        }


@dataclass(frozen=True)
class Cost:
    """`meta.cost`. A null value always has a note; zero means measured zero."""

    elapsed_s: float
    content_bytes_read: int | None
    entries_visited: int | None
    subprocess_calls: int | None
    subprocess_stdout_bytes: int | None
    subprocess_content_bytes_read: int | None
    notes: Mapping[str, str] = EMPTY

    def __post_init__(self) -> None:
        _freeze_fields(self, "notes")
        nulls = {name for name in COST_NULLABLE if getattr(self, name) is None}
        if nulls != set(self.notes):
            raise ValueError(
                f"cost needs exactly one note per null field: nulls={sorted(nulls)}, "
                f"notes={sorted(self.notes)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "elapsed_s": self.elapsed_s,
            **{name: getattr(self, name) for name in COST_NULLABLE},
            "notes": dict(self.notes),
        }


@dataclass(frozen=True)
class Tool:
    """`meta.tool`."""

    name: str = TOOL_NAME
    version: str = __version__

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version}


def derive_status(
    coverage: Sequence[CoverageEntry], unavailable: Sequence[UnavailableSource]
) -> str:
    """`partial` on any coverage gap or failed or timed-out source."""
    if coverage or any(s.reason in PARTIAL_SOURCE_REASONS for s in unavailable):
        return "partial"
    return "complete"


@dataclass(frozen=True)
class Meta:
    """`meta`; `status` is derived from coverage and sources, never stored."""

    command: str
    captured_at: str
    scope: Scope
    cost: Cost
    incomplete_coverage: tuple[CoverageEntry, ...] = ()
    unavailable_sources: tuple[UnavailableSource, ...] = ()
    tool: Tool = field(default_factory=Tool)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _freeze_fields(self, "incomplete_coverage", "unavailable_sources")

    @property
    def status(self) -> str:
        return derive_status(self.incomplete_coverage, self.unavailable_sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": self.tool.to_dict(),
            "command": self.command,
            "captured_at": self.captured_at,
            "status": self.status,
            "scope": self.scope.to_dict(),
            "cost": self.cost.to_dict(),
            "incomplete_coverage": [e.to_dict() for e in self.incomplete_coverage],
            "unavailable_sources": [s.to_dict() for s in self.unavailable_sources],
        }


@dataclass(frozen=True)
class Data:
    """`data`: summary, findings, check-specific sections, then suggestions."""

    summary: Mapping[str, Any]
    findings: tuple[Finding, ...] = ()
    suggestions: tuple[Suggestion, ...] = ()
    extra: Mapping[str, Any] = EMPTY

    def __post_init__(self) -> None:
        clash = {"summary", "findings", "suggestions"} & set(self.extra)
        if clash:
            raise ValueError(f"extra repeats a fixed data key: {sorted(clash)}")
        _freeze_fields(self, "summary", "findings", "suggestions", "extra")

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": thaw(self.summary),
            "findings": [finding.to_dict() for finding in self.findings],
            **thaw(self.extra),
            "suggestions": [suggestion.to_dict() for suggestion in self.suggestions],
        }


@dataclass(frozen=True)
class Envelope:
    """`{data, meta}`, printed once per successful command."""

    data: Data
    meta: Meta

    def to_dict(self) -> dict[str, Any]:
        return {"data": self.data.to_dict(), "meta": self.meta.to_dict()}


@dataclass(frozen=True)
class ErrorInfo:
    """The error object on stderr; `code` follows from `exit_code`."""

    error: str
    reason: str
    suggestion: str
    help: str
    exit_code: int
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.exit_code not in EXIT_CODES.values():
            raise ValueError(f"no error code for exit code {self.exit_code}")

    @property
    def code(self) -> str:
        return next(k for k, v in EXIT_CODES.items() if v == self.exit_code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "error": self.error,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "help": self.help,
            "code": self.code,
            "exit_code": self.exit_code,
        }


def order_findings_by_size(
    findings: Iterable[Finding], key: str = "allocated_bytes"
) -> tuple[Finding, ...]:
    """Size key descending (null last), then target by code point."""

    def sort_key(finding: Finding) -> tuple[bool, int, str]:
        size = getattr(finding, key)
        return (size is None, -(size or 0), finding.target)

    return tuple(sorted(findings, key=sort_key))


def order_suggestions(suggestions: Iterable[Suggestion]) -> tuple[Suggestion, ...]:
    """Risk (low, medium, high), then id."""
    return tuple(sorted(suggestions, key=lambda s: (RISKS.index(s.risk), s.id)))


def order_coverage(entries: Iterable[CoverageEntry]) -> tuple[CoverageEntry, ...]:
    """`path`, then `reason`."""
    return tuple(sorted(entries, key=lambda e: (e.path, e.reason)))


def order_unavailable(
    sources: Iterable[UnavailableSource],
) -> tuple[UnavailableSource, ...]:
    """`source`."""
    return tuple(sorted(sources, key=lambda s: s.source))


def order_roots(roots: Iterable[ScopeRoot]) -> tuple[ScopeRoot, ...]:
    """`path` ascending; identical resolved roots merge, first given wins."""
    merged: dict[str, ScopeRoot] = {}
    for root in roots:
        merged.setdefault(root.path, root)
    return tuple(sorted(merged.values(), key=lambda r: r.path))


def _positions(ids: Iterable[str]) -> dict[str, int]:
    return {item: index for index, item in enumerate(ids)}


def _ordered_ids(ids: Iterable[str], positions: Mapping[str, int]) -> tuple[str, ...]:
    missing = [item for item in ids if item not in positions]
    if missing:
        raise ValueError(f"reference to unknown ID: {missing}")
    return tuple(sorted(ids, key=positions.__getitem__))


def link_references(
    findings: Sequence[Finding], suggestions: Sequence[Suggestion]
) -> tuple[tuple[Finding, ...], tuple[Suggestion, ...]]:
    """Order `suggestion_ids` by suggestion order and `finding_ids` by finding
    order, rejecting dangling references. Returns new objects."""
    by_suggestion = _positions(s.id for s in suggestions)
    by_finding = _positions(f.id for f in findings)
    new_findings = tuple(
        replace(f, suggestion_ids=_ordered_ids(f.suggestion_ids, by_suggestion))
        for f in findings
    )
    new_suggestions = tuple(
        replace(s, finding_ids=_ordered_ids(s.finding_ids, by_finding))
        for s in suggestions
    )
    return new_findings, new_suggestions
