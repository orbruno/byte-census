"""`byte-census docker scan`: what Docker reports it occupies.

Four read-only argvs from the allowlist run through the runner: `system df`,
`images`, dangling image IDs, and exited containers. All figures are
Docker-reported and informational; they are never host filesystem bytes, so
every finding keeps `logical_bytes`, `allocated_bytes`, and
`reclaimable_estimate_bytes` null (quantities.md, Docker figures). A missing
CLI or a stopped daemon exits 4; the other three sources only add
`unavailable_sources` entries.
"""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import click

from byte_census import runner
from byte_census.checks.docker_sizes import (
    docker_created_at,
    parse_docker_size,
    parse_reclaimable,
)
from byte_census.command import CheckResult, format_option, run_observation
from byte_census.cost import CostCounters
from byte_census.errors import SourceUnavailableError
from byte_census.model import (
    Classification,
    Data,
    Finding,
    Suggestion,
    UnavailableSource,
    finding_id,
)
from byte_census.runner import RunnerError, RunResult
from byte_census.suggestions import build_check_wide

COMMAND = "docker scan"
NOTE = "Docker-reported figures; never added to host filesystem totals."
DF = ("docker", "system", "df", "--format", "{{json .}}")
IMAGES = ("docker", "images", "--format", "{{json .}}")
DANGLING = ("docker", "images", "-f", "dangling=true", "-q")
PS = ("docker", "ps", "-a", "-f", "status=exited", "--format", "{{json .}}")
SOURCE_NAMES = {
    DF: "docker system df",
    IMAGES: "docker images",
    DANGLING: "docker images -f dangling=true -q",
    PS: "docker ps -a -f status=exited",
}
TYPE_ORDER = ("Images", "Containers", "Local Volumes", "Build Cache")
SUGGESTIONS_BY_TYPE: Mapping[str, tuple[str, ...]] = {
    "Images": ("docker-image-prune", "docker-system-prune-all"),
    "Containers": ("docker-container-prune", "docker-system-prune-all"),
    "Local Volumes": ("docker-volume-prune",),
    "Build Cache": ("docker-system-prune-all",),
}
CATALOG_ORDER = (
    "docker-image-prune",
    "docker-container-prune",
    "docker-system-prune-all",
    "docker-volume-prune",
)
SHORT_ID = 12
IMAGE_ID = re.compile(r"^(sha256:)?[0-9a-f]{12,64}$")
DF_REQUIRED = ("Type", "TotalCount", "Size", "Reclaimable")
IMAGE_REQUIRED = ("Repository", "Tag", "ID", "Size")
PS_REQUIRED = ("Names", "ID", "Image", "Status")

Run = Callable[[Sequence[str]], RunResult]


def run_allowlisted(argv: Sequence[str]) -> RunResult:
    """The default `Run`: the runner, which rejects any non-allowlisted argv."""
    return runner.run(argv)


class _Unreadable(Exception):
    """An optional source answered, but not in a usable form."""


@dataclass(frozen=True)
class _Reading:
    """Rows of one source, or why it gave none, plus the stdout it produced."""

    rows: tuple[Any, ...] = ()
    problem: UnavailableSource | None = None
    stdout_bytes: int = 0
    called: bool = True


def _unavailable(argv: tuple[str, ...], reason: str, detail: str) -> UnavailableSource:
    return UnavailableSource(SOURCE_NAMES[argv], reason, detail)


def _df_error(reason: str, missing: bool = False) -> SourceUnavailableError:
    fix = (
        "Install Docker or add it to PATH"
        if missing
        else "Start Docker Desktop or the Docker daemon"
    )
    return SourceUnavailableError(
        error="docker scan could not read Docker disk usage",
        reason=reason,
        suggestion=f"{fix}, then run `byte-census docker scan` again.",
    )


def _stderr_line(result: RunResult) -> str:
    text = result.stderr.strip()
    return f": {text}" if text else ""


def _json_rows(text: str) -> tuple[dict[str, Any], ...]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise _Unreadable(f"a line is not valid JSON: {error.msg}") from error
        except (ValueError, RecursionError) as error:
            raise _Unreadable("a line is too large or too deeply nested") from error
        if not isinstance(row, dict):
            raise _Unreadable("a line is not a JSON object")
        rows.append(row)
    return tuple(rows)


def _read_df(run: Run) -> _Reading:
    try:
        result = run(DF)
    except RunnerError as error:
        missing = error.reason == "not_installed"
        raise _df_error(str(error), missing) from error
    if not result.ok:
        status = f"`docker system df` exited with status {result.returncode}"
        raise _df_error(status + _stderr_line(result))
    try:
        rows = _json_rows(result.stdout)
    except _Unreadable as error:
        raise _df_error(
            f"`docker system df` output is not valid JSON: {error}"
        ) from error
    valid, dropped = _split_rows(rows, DF_REQUIRED, "Type")
    if not valid:
        raise _df_error(
            "`docker system df` output is unusable: " + (dropped or "it has no rows")
        )
    problem = _unavailable(DF, "failed", dropped) if dropped else None
    return _Reading(valid, problem, result.stdout_bytes)


def _split_rows(
    rows: Sequence[dict[str, Any]], required: tuple[str, ...], label: str
) -> tuple[tuple[dict[str, Any], ...], str]:
    """Rows with every required string field, and a note naming the rest."""
    valid, notes = [], []
    for row in rows:
        missing = [k for k in required if not isinstance(row.get(k), str)]
        if missing:
            name = row.get(label) if isinstance(row.get(label), str) else "?"
            notes.append(f"row {name} lacks {', '.join(missing)}")
        else:
            valid.append(row)
    return tuple(valid), "; ".join(notes)


def _read_optional(
    run: Run, argv: tuple[str, ...], required: tuple[str, ...] | None
) -> _Reading:
    try:
        result = run(argv)
    except RunnerError as error:
        return _Reading(problem=_unavailable(argv, error.reason, str(error)))
    if not result.ok:
        detail = f"exited with status {result.returncode}{_stderr_line(result)}"
        problem = _unavailable(argv, "failed", detail)
        return _Reading(problem=problem, stdout_bytes=result.stdout_bytes)
    try:
        rows = (
            _plain_rows(result.stdout)
            if required is None
            else _json_rows(result.stdout)
        )
        if required is not None:
            rows = _usable_rows(rows, required)
        else:
            rows = _usable_ids(rows)
    except _Unreadable as error:
        problem = _unavailable(argv, "failed", f"unusable output: {error}")
        return _Reading(problem=problem, stdout_bytes=result.stdout_bytes)
    return _Reading(rows, None, result.stdout_bytes)


def _usable_rows(
    rows: Sequence[dict[str, Any]], required: tuple[str, ...]
) -> tuple[dict[str, Any], ...]:
    valid, dropped = _split_rows(rows, required, required[0])
    if dropped:
        raise _Unreadable(dropped)
    return valid


def _usable_ids(rows: Sequence[str]) -> tuple[str, ...]:
    odd = [row for row in rows if not IMAGE_ID.match(row)]
    if odd:
        raise _Unreadable(f"{odd[0]!r} is not an image ID")
    return tuple(rows)


def _plain_rows(text: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(line.strip() for line in text.splitlines() if line.strip())
    )


def _int_or_none(raw: Any) -> int | None:
    try:
        return int(str(raw))
    except ValueError:
        return None


def _unparsed(row: dict[str, Any], details: Mapping[str, Any]) -> list[str]:
    """Notes naming each numeric field of a type that could not be parsed."""
    fields = {
        "TotalCount": "total_count",
        "Active": "active_count",
        "Size": "docker_reported_size_bytes",
        "Reclaimable": "docker_reported_reclaimable_bytes",
    }
    return [
        f"{details['docker_type']} {raw} is not a number"
        for raw, key in fields.items()
        if details[key] is None and (raw != "Active" or "Active" in row)
    ]


def _type_finding(row: dict[str, Any]) -> Finding:
    kind_name = str(row.get("Type", ""))
    target = f"docker:{kind_name}"
    size, reclaim = str(row.get("Size", "")), str(row.get("Reclaimable", ""))
    return Finding(
        id=finding_id("dkr", "docker_type", target),
        kind="docker_type",
        target=target,
        caveats=("docker_reported_not_host",),
        suggestion_ids=SUGGESTIONS_BY_TYPE.get(kind_name, ()),
        classification=Classification(owner="docker"),
        details={
            "docker_type": kind_name,
            "total_count": _int_or_none(row.get("TotalCount")),
            "active_count": _int_or_none(row.get("Active")),
            "docker_reported_size_bytes": parse_docker_size(size),
            "docker_reported_reclaimable_bytes": parse_reclaimable(reclaim),
            "raw": {"Size": size, "Reclaimable": reclaim},
        },
    )


def _type_rank(finding: Finding) -> tuple[int, str]:
    name = finding.details["docker_type"]
    rank = TYPE_ORDER.index(name) if name in TYPE_ORDER else len(TYPE_ORDER)
    return (rank, name)


def _findings(rows: Sequence[dict[str, Any]]) -> tuple[Finding, ...]:
    return tuple(sorted((_type_finding(r) for r in rows), key=_type_rank))


def _number_notes(rows: Sequence[dict[str, Any]]) -> list[str]:
    return [note for row in rows for note in _unparsed(row, _type_finding(row).details)]


def _suggestions(findings: Sequence[Finding]) -> tuple[Suggestion, ...]:
    related: dict[str, list[str]] = {}
    for finding in findings:
        for sid in finding.suggestion_ids:
            related.setdefault(sid, []).append(finding.id)
    return tuple(
        build_check_wide(sid, related[sid]) for sid in CATALOG_ORDER if sid in related
    )


def _short_id(raw: Any) -> str:
    text = str(raw)
    return text.removeprefix("sha256:")[:SHORT_ID]


def _image(row: dict[str, Any]) -> dict[str, Any]:
    raw = str(row.get("Size", ""))
    return {
        "repository": str(row.get("Repository", "")),
        "tag": str(row.get("Tag", "")),
        "image_id": _short_id(row.get("ID", "")),
        "docker_reported_size_bytes": parse_docker_size(raw),
        "raw_size": raw,
        "created_at": docker_created_at(str(row.get("CreatedAt", ""))),
    }


def _image_rank(image: dict[str, Any]) -> tuple[bool, int, str, str, str]:
    size = image["docker_reported_size_bytes"]
    return (
        size is None,
        -(size or 0),
        image["repository"],
        image["tag"],
        image["image_id"],
    )


def _container(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(row.get("Names", "")),
        "image": str(row.get("Image", "")),
        "container_id": _short_id(row.get("ID", "")),
        "status": str(row.get("Status", "")),
        "created_at": docker_created_at(str(row.get("CreatedAt", ""))),
    }


def _total(findings: Sequence[Finding], key: str) -> int | None:
    """Sum of a field, or null when any component is unknown."""
    values = [f.details[key] for f in findings]
    return None if any(v is None for v in values) else sum(values)


def _summary(
    findings: Sequence[Finding], dangling: int, stopped: int
) -> dict[str, Any]:
    return {
        "informational": True,
        "daemon_available": True,
        "dangling_image_count": dangling,
        "stopped_container_count": stopped,
        "docker_reported_size_bytes": _total(findings, "docker_reported_size_bytes"),
        "docker_reported_reclaimable_bytes": _total(
            findings, "docker_reported_reclaimable_bytes"
        ),
        "note": NOTE,
    }


def _with_notes(
    reading: _Reading, notes: Sequence[str], argv: tuple[str, ...]
) -> _Reading:
    """Mark a source partial when parsed rows hold fields that are not numbers."""
    if not notes:
        return reading
    earlier = [reading.problem.detail] if reading.problem is not None else []
    detail = "; ".join([*earlier, *notes])
    return replace(reading, problem=_unavailable(argv, "failed", detail))


def _image_notes(rows: Sequence[dict[str, Any]]) -> list[str]:
    sizes = [
        f"image {row.get('ID')} Size is not a number"
        for row in rows
        if parse_docker_size(str(row["Size"])) is None
    ]
    return sizes + _date_notes("image", rows)


def _date_notes(label: str, rows: Sequence[dict[str, Any]]) -> list[str]:
    """Notes for CreatedAt values present but not a recognizable date."""
    return [
        f"{label} {row.get('ID')} CreatedAt is not a date"
        for row in rows
        if row.get("CreatedAt")
        and not docker_created_at(str(row["CreatedAt"])).endswith("Z")
    ]


def docker_check(run: Run) -> CheckResult:
    """Run the four reads and assemble the result."""
    usage = _read_df(run)
    images = _read_optional(run, IMAGES, IMAGE_REQUIRED)
    dangling = _read_optional(run, DANGLING, None)
    stopped = _read_optional(run, PS, PS_REQUIRED)
    usage = _with_notes(usage, _number_notes(usage.rows), DF)
    images = _with_notes(images, _image_notes(images.rows), IMAGES)
    stopped = _with_notes(stopped, _date_notes("container", stopped.rows), PS)
    findings = _findings(usage.rows)
    data = Data(
        summary=_summary(findings, len(dangling.rows), len(stopped.rows)),
        findings=findings,
        suggestions=_suggestions(findings),
        extra={
            "images": sorted((_image(r) for r in images.rows), key=_image_rank),
            "stopped_containers": sorted(
                (_container(r) for r in stopped.rows),
                key=lambda c: (c["name"], c["container_id"]),
            ),
        },
    )
    readings = (usage, images, dangling, stopped)
    counters = CostCounters()
    for reading in readings:
        counters = counters.add_subprocess_call(reading.stdout_bytes)
    problems = tuple(r.problem for r in readings if r.problem is not None)
    return CheckResult(data=data, counters=counters, unavailable_sources=problems)


@click.group(
    "docker",
    context_settings={"help_option_names": ["--help", "-h"]},
)
def docker() -> None:
    """
    Observe Docker's own disk accounting.

    Example:

      \b
      # What Docker says it occupies
      byte-census docker scan
    """


@docker.command("scan")
@format_option
@click.pass_context
def scan(ctx: click.Context, output_format: str) -> None:
    """
    Report Docker disk usage, images, and stopped containers.

    Figures are Docker-reported and are never added to host totals. Exits 4 when
    the Docker CLI is missing or the daemon is not running. Nothing is changed.

    Example:

      \b
      byte-census docker scan --format table
    """
    run_observation(
        ctx,
        COMMAND,
        output_format,
        lambda: docker_check(lambda argv: run_allowlisted(argv)),
    )
