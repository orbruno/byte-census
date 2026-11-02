"""Model shapes, immutability, IDs, and ordering helpers (WI-CORE AC-01, AC-02)."""

import dataclasses
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from byte_census.model import (
    SCHEMA_VERSION,
    Classification,
    Cost,
    CoverageEntry,
    Data,
    Envelope,
    ErrorInfo,
    Finding,
    Meta,
    Scope,
    ScopeRoot,
    Suggestion,
    Tool,
    UnavailableSource,
    derive_status,
    finding_id,
    format_captured_at,
    link_references,
    order_coverage,
    order_findings_by_size,
    order_roots,
    order_suggestions,
    order_unavailable,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "contracts" / "examples"
ENVELOPE_EXAMPLES = [
    "artifacts-scan",
    "caches-scan",
    "disk-map",
    "docker-scan",
    "duplicates-scan",
]
DATA_KEYS = ("summary", "findings", "suggestions")


def load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def finding_from(raw: dict[str, Any]) -> Finding:
    return Finding(
        id=raw["id"],
        kind=raw["kind"],
        target=raw["target"],
        logical_bytes=raw["logical_bytes"],
        allocated_bytes=raw["allocated_bytes"],
        reclaimable_estimate_bytes=raw["reclaimable_estimate_bytes"],
        caveats=tuple(raw["caveats"]),
        see_check=raw["see_check"],
        suggestion_ids=tuple(raw["suggestion_ids"]),
        classification=Classification(**raw["classification"]),
        details=raw["details"],
    )


def suggestion_from(raw: dict[str, Any]) -> Suggestion:
    return Suggestion(
        id=raw["id"],
        command=raw["command"],
        risk=raw["risk"],
        reversible=raw["reversible"],
        reason=raw["reason"],
        finding_ids=tuple(raw["finding_ids"]),
        requires_owner_authorization=raw["requires_owner_authorization"],
    )


def meta_from(raw: dict[str, Any]) -> Meta:
    scope = raw["scope"]
    return Meta(
        tool=Tool(**raw["tool"]),
        command=raw["command"],
        captured_at=raw["captured_at"],
        scope=Scope(
            roots=tuple(ScopeRoot(**root) for root in scope["roots"]),
            options=scope["options"],
            skipped_mounts=tuple(scope["skipped_mounts"]),
        ),
        cost=Cost(**raw["cost"]),
        incomplete_coverage=tuple(
            CoverageEntry(**entry) for entry in raw["incomplete_coverage"]
        ),
        unavailable_sources=tuple(
            UnavailableSource(**entry) for entry in raw["unavailable_sources"]
        ),
        schema_version=raw["schema_version"],
    )


def envelope_from(raw: dict[str, Any]) -> Envelope:
    data = raw["data"]
    extra = {key: value for key, value in data.items() if key not in DATA_KEYS}
    return Envelope(
        data=Data(
            summary=data["summary"],
            findings=tuple(finding_from(item) for item in data["findings"]),
            suggestions=tuple(suggestion_from(item) for item in data["suggestions"]),
            extra=extra,
        ),
        meta=meta_from(raw["meta"]),
    )


def ordered(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


@pytest.mark.parametrize("name", ENVELOPE_EXAMPLES)
def test_envelope_serializes_to_example_in_exact_field_order(name: str) -> None:
    raw = load(name)

    result = envelope_from(raw).to_dict()

    assert ordered(result) == ordered(raw)


def test_duplicates_envelope_keys_match_example_order() -> None:
    raw = load("duplicates-scan")

    result = envelope_from(raw).to_dict()

    assert list(result) == ["data", "meta"]
    assert list(result["meta"]) == list(raw["meta"])
    assert list(result["data"]["findings"][0]) == list(raw["data"]["findings"][0])
    assert list(result["meta"]["cost"]) == list(raw["meta"]["cost"])


def test_error_object_matches_example() -> None:
    raw = load("error")
    info = ErrorInfo(
        error=raw["error"],
        reason=raw["reason"],
        suggestion=raw["suggestion"],
        help=raw["help"],
        exit_code=raw["exit_code"],
    )

    assert ordered(info.to_dict()) == ordered(raw)
    assert info.code == "source_unavailable"


@pytest.mark.parametrize(
    ("exit_code", "code"),
    [(1, "internal_error"), (2, "usage_error"), (3, "validation_error")],
)
def test_error_code_follows_exit_code(exit_code: int, code: str) -> None:
    info = ErrorInfo("e", "r", "s", "h", exit_code)

    assert info.code == code
    assert info.to_dict()["exit_code"] == exit_code


@pytest.mark.parametrize("exit_code", [0, 5, -1])
def test_error_rejects_exit_codes_without_a_code(exit_code: int) -> None:
    with pytest.raises(ValueError, match="exit code"):
        ErrorInfo("e", "r", "s", "h", exit_code)


def test_classification_defaults_follow_contract() -> None:
    assert dataclasses.asdict(Classification()) == {
        "owner": "",
        "status": "unknown",
        "recovery": "unknown",
        "confidence": "low",
        "disposition": "investigate",
    }


def test_finding_defaults_carry_classification_and_empty_links() -> None:
    finding = Finding(id="x", kind="k", target="/t")

    result = finding.to_dict()

    assert result["classification"]["disposition"] == "investigate"
    assert result["caveats"] == []
    assert result["suggestion_ids"] == []
    assert result["see_check"] is None
    assert result["details"] == {}
    assert result["logical_bytes"] is None


def test_finding_is_frozen_and_details_are_read_only() -> None:
    details = {"files": [{"path": "/a"}]}
    finding = Finding(id="x", kind="k", target="/t", details=details)

    with pytest.raises(dataclasses.FrozenInstanceError):
        finding.kind = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        finding.details["new"] = 1  # type: ignore[index]
    details["files"][0]["path"] = "/changed"
    assert finding.to_dict()["details"] == {"files": [{"path": "/a"}]}


def test_serialized_dicts_are_independent_copies() -> None:
    finding = Finding(id="x", kind="k", target="/t", details={"a": [1]})

    first = finding.to_dict()
    first["details"]["a"].append(2)

    assert finding.to_dict()["details"] == {"a": [1]}


@pytest.mark.parametrize(
    "build",
    [
        lambda: Suggestion("s", "c", "low", True, "r"),
        lambda: CoverageEntry("/p", "dataless", None, "lstat"),
        lambda: UnavailableSource("npm", "not_installed", "d"),
        lambda: ScopeRoot("/p", "~/p", 1),
        lambda: Tool(),
        lambda: Scope(),
        lambda: Classification(),
    ],
)
def test_model_objects_are_frozen(build: Any) -> None:
    obj = build()
    name = dataclasses.fields(obj)[0].name

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(obj, name, "changed")


def test_scope_options_are_read_only() -> None:
    scope = Scope(options={"top": 30})

    with pytest.raises(TypeError):
        scope.options["top"] = 1  # type: ignore[index]


def test_finding_id_rule() -> None:
    target = "sha256:49a4e69a0038aaab493b9605d21d7add1df8519e18d76c621fa0d6f9e98eb35b"

    assert finding_id("dup", "duplicate_group", target) == "dup-64731b5cc4fd"


def test_finding_id_rejects_unknown_prefix() -> None:
    with pytest.raises(ValueError, match="prefix"):
        finding_id("zzz", "k", "t")


def test_tool_defaults_to_package_identity() -> None:
    assert Tool().to_dict() == {"name": "byte-census", "version": "2.0.0"}
    assert SCHEMA_VERSION == "1.0.0"


@pytest.mark.parametrize(
    ("coverage", "unavailable", "status"),
    [
        ((), (), "complete"),
        ((), (UnavailableSource("npm", "not_installed", "d"),), "complete"),
        ((), (UnavailableSource("diskutil", "not_running", "d"),), "complete"),
        ((), (UnavailableSource("tmutil", "failed", "d"),), "partial"),
        ((), (UnavailableSource("tmutil", "timed_out", "d"),), "partial"),
        ((CoverageEntry("/p", "dataless", None, "lstat"),), (), "partial"),
    ],
)
def test_status_rules(coverage: Any, unavailable: Any, status: str) -> None:
    assert derive_status(coverage, unavailable) == status


@pytest.mark.parametrize("name", ENVELOPE_EXAMPLES)
def test_example_status_matches_rule(name: str) -> None:
    meta = envelope_from(load(name)).meta

    assert meta.status == load(name)["meta"]["status"]


def test_captured_at_is_utc_with_z() -> None:
    moment = datetime(
        2026, 11, 2, 10, 30, 0, 999_999, tzinfo=timezone(timedelta(hours=1))
    )

    assert format_captured_at(moment) == "2026-11-02T09:30:00Z"
    assert (
        format_captured_at(datetime(2026, 1, 2, tzinfo=UTC)) == "2026-01-02T00:00:00Z"
    )


def test_captured_at_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        format_captured_at(datetime(2026, 1, 2))


def test_order_findings_by_size_desc_then_target_code_point() -> None:
    items = (
        Finding("1", "k", "/b", allocated_bytes=10),
        Finding("2", "k", "/a", allocated_bytes=10),
        Finding("3", "k", "/Z", allocated_bytes=10),
        Finding("4", "k", "/c", allocated_bytes=99),
        Finding("5", "k", "/n", allocated_bytes=None),
    )

    result = order_findings_by_size(items)

    assert [f.target for f in result] == ["/c", "/Z", "/a", "/b", "/n"]


def test_order_findings_by_size_accepts_logical_key() -> None:
    items = (
        Finding("1", "large_file", "/a", logical_bytes=5, allocated_bytes=9),
        Finding("2", "large_file", "/b", logical_bytes=8, allocated_bytes=1),
    )

    result = order_findings_by_size(items, key="logical_bytes")

    assert [f.target for f in result] == ["/b", "/a"]


def test_order_suggestions_by_risk_then_id() -> None:
    items = (
        Suggestion("b", "c", "high", False, "r"),
        Suggestion("z", "c", "low", False, "r"),
        Suggestion("a", "c", "high", False, "r"),
        Suggestion("m", "c", "medium", False, "r"),
    )

    assert [s.id for s in order_suggestions(items)] == ["z", "m", "a", "b"]


def test_order_coverage_unavailable_and_roots() -> None:
    coverage = (
        CoverageEntry("/b", "vanished", None, "lstat"),
        CoverageEntry("/a", "read_error", "EIO", "read"),
        CoverageEntry("/a", "dataless", None, "lstat"),
    )
    sources = (
        UnavailableSource("uv", "failed", "d"),
        UnavailableSource("brew", "not_installed", "d"),
    )
    roots = (
        ScopeRoot("/b", "b", 1),
        ScopeRoot("/a", "a", 1),
        ScopeRoot("/a", "./a", 1),
    )

    assert [(c.path, c.reason) for c in order_coverage(coverage)] == [
        ("/a", "dataless"),
        ("/a", "read_error"),
        ("/b", "vanished"),
    ]
    assert [s.source for s in order_unavailable(sources)] == ["brew", "uv"]
    assert [(r.path, r.given) for r in order_roots(roots)] == [("/a", "a"), ("/b", "b")]


@pytest.mark.parametrize("name", ENVELOPE_EXAMPLES)
def test_examples_follow_meta_and_suggestion_ordering(name: str) -> None:
    envelope = envelope_from(load(name))
    meta = envelope.meta

    assert order_suggestions(envelope.data.suggestions) == envelope.data.suggestions
    assert order_coverage(meta.incomplete_coverage) == meta.incomplete_coverage
    assert order_unavailable(meta.unavailable_sources) == meta.unavailable_sources
    assert order_roots(meta.scope.roots) == meta.scope.roots


def test_link_references_orders_cross_links() -> None:
    findings = (
        Finding("f1", "k", "/a", suggestion_ids=("s2", "s1")),
        Finding("f2", "k", "/b", suggestion_ids=("s1",)),
    )
    suggestions = (
        Suggestion("s1", "c", "low", True, "r", finding_ids=("f2", "f1")),
        Suggestion("s2", "c", "high", False, "r", finding_ids=("f1",)),
    )

    linked_findings, linked_suggestions = link_references(findings, suggestions)

    assert linked_findings[0].suggestion_ids == ("s1", "s2")
    assert linked_suggestions[0].finding_ids == ("f1", "f2")
    assert findings[0].suggestion_ids == ("s2", "s1")


def test_link_references_rejects_dangling_ids() -> None:
    findings = (Finding("f1", "k", "/a", suggestion_ids=("missing",)),)

    with pytest.raises(ValueError, match="missing"):
        link_references(findings, ())


@pytest.mark.parametrize("name", ENVELOPE_EXAMPLES)
def test_examples_cross_links_are_already_ordered(name: str) -> None:
    data = envelope_from(load(name)).data

    findings, suggestions = link_references(data.findings, data.suggestions)

    assert findings == data.findings
    assert suggestions == data.suggestions
