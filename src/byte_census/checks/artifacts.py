"""`byte-census artifacts scan ROOT` (WI-ARTIFACTS).

Reports regenerable development folders (`node_modules`, `.venv`, `venv`,
`target` beside `Cargo.toml`) with allocated size, the project's modification
time, and a medium-risk remove-and-regenerate suggestion. Discovery lives in
`artifacts_discover`, the per-artifact sizing walk in `artifacts_size`.
"""

from collections import Counter
from datetime import UTC, datetime

import click

from byte_census import fsread
from byte_census.checks.artifacts_discover import (
    REGENERATE,
    Artifact,
    Discovery,
    discover,
)
from byte_census.checks.artifacts_size import (
    InodeKey,
    Measure,
    measure_subtree,
    vanished,
)
from byte_census.command import CheckResult, format_option, run_observation
from byte_census.cost import CostCounters
from byte_census.model import (
    Classification,
    CoverageEntry,
    Data,
    Finding,
    Scope,
    ScopeRoot,
    Suggestion,
    finding_id,
    format_captured_at,
    order_findings_by_size,
)
from byte_census.paths import validate_root
from byte_census.suggestions import build_artifact_suggestion

COMMAND = "artifacts scan"
CLONE_CAVEAT = "apfs_clone_or_shared_extent"
LINKS_CAVEAT = "hard_links_merged"
MeasuredArtifact = tuple[Artifact, Measure]


def measure_artifact(path: str, claimed: frozenset[InodeKey]) -> Measure:
    """Size one artifact, turning a vanished or unreadable folder into coverage."""
    try:
        return measure_subtree(path, claimed)
    except OSError as error:
        return vanished(path, error)


def _measure_all(artifacts: tuple[Artifact, ...]) -> tuple[MeasuredArtifact, ...]:
    """Measure in byte order of path so hard-link attribution is deterministic."""
    claimed: frozenset[InodeKey] = frozenset()
    measured: list[MeasuredArtifact] = []
    for artifact in artifacts:
        measure = measure_artifact(artifact.path, claimed)
        claimed = claimed | measure.inodes
        measured.append((artifact, measure))
    return tuple(measured)


def _shared_links(measured: tuple[MeasuredArtifact, ...]) -> frozenset[InodeKey]:
    """Multi-name inodes seen by more than one artifact."""
    seen = Counter(key for _, m in measured for key in m.linked)
    return frozenset(key for key, count in seen.items() if count > 1)


def _caveats(measure: Measure, shared: frozenset[InodeKey]) -> tuple[str, ...]:
    merged = measure.repeated or bool(measure.linked & shared)
    return (CLONE_CAVEAT, LINKS_CAVEAT) if merged else (CLONE_CAVEAT,)


def _iso(moment: float) -> str:
    return format_captured_at(datetime.fromtimestamp(moment, UTC))


def _finding(
    artifact: Artifact, measure: Measure, shared: frozenset[InodeKey]
) -> Finding:
    fid = finding_id("art", "artifact", artifact.path)
    return Finding(
        id=fid,
        kind="artifact",
        target=artifact.path,
        logical_bytes=measure.logical_bytes,
        allocated_bytes=measure.allocated_bytes,
        reclaimable_estimate_bytes=measure.allocated_bytes,
        caveats=_caveats(measure, shared),
        suggestion_ids=(f"artifact-remove-regenerate@{fid}",),
        classification=Classification(owner=artifact.project),
        details={
            "artifact_kind": artifact.kind,
            "project": artifact.project,
            "regenerate_command": REGENERATE[artifact.kind],
            "project_mtime": _iso(artifact.project_mtime),
        },
    )


def _suggestion(finding: Finding, artifact: Artifact) -> Suggestion:
    return build_artifact_suggestion(
        finding.id, artifact.path, artifact.project, REGENERATE[artifact.kind]
    )


def _coverage(errors: tuple[fsread.WalkError, ...]) -> tuple[CoverageEntry, ...]:
    return tuple(
        CoverageEntry(e.path, e.reason, e.errno_name, e.operation) for e in errors
    )


def _usable(measured: tuple[MeasuredArtifact, ...]) -> tuple[MeasuredArtifact, ...]:
    """Drop artifacts that vanished before they could be sized."""
    return tuple((a, m) for a, m in measured if m.opened)


def _data(measured: tuple[MeasuredArtifact, ...]) -> Data:
    shared = _shared_links(measured)
    pairs = tuple((_finding(a, m, shared), a) for a, m in _usable(measured))
    findings = order_findings_by_size(f for f, _ in pairs)
    summary = {
        "artifact_count": len(findings),
        "total_allocated_bytes": sum(m.counted_allocated_bytes for _, m in measured),
    }
    return Data(
        summary=summary,
        findings=findings,
        suggestions=tuple(_suggestion(f, a) for f, a in pairs),
    )


def artifacts_check(root_argument: str) -> CheckResult:
    """Discover artifacts below the root and size each one."""
    root = str(validate_root(root_argument))
    scope_root = ScopeRoot(root, root_argument, fsread.lstat(root).st_dev)
    found: Discovery = discover(root)
    measured = _measure_all(found.artifacts)
    errors = found.errors + tuple(e for _, m in measured for e in m.errors)
    mounts = found.mounts + tuple(x for _, m in measured for x in m.mounts)
    visited = found.visited + sum(m.visited for _, m in measured)
    return CheckResult(
        data=_data(measured),
        scope=Scope(
            roots=(scope_root,),
            skipped_mounts=tuple(sorted(mount.path for mount in mounts)),
        ),
        counters=CostCounters().add_entries(visited),
        incomplete_coverage=_coverage(errors),
    )


@click.group("artifacts")
def artifacts() -> None:
    """
    Find regenerable development folders.

    Example:

      \b
      byte-census artifacts scan ~/Projects
    """


@artifacts.command("scan")
@click.argument("root")
@format_option
@click.pass_context
def scan(ctx: click.Context, root: str, output_format: str) -> None:
    """
    List node_modules, .venv, venv, and target folders under ROOT.

    Each one is reported with its allocated size, its project, the project's
    modification time, and the command that regenerates it. Nothing is
    removed; the removal command is a suggestion only.

    Example:

      \b
      byte-census artifacts scan ~/Projects --format table
    """
    run_observation(ctx, COMMAND, output_format, lambda: artifacts_check(root))
