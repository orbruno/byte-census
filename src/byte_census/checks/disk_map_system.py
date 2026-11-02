"""System context for `disk map` (`data.system`, parity matrix S14, S15, S22, S23).

Optional sources, each through the runner with its exact allowlisted argv:
`df -k /` (system volume), `diskutil info /`, `tmutil listlocalsnapshots /`
(count only), and `docker system df --format {{json .}}` (informational,
never added to host totals). A source that is missing, fails, times out, or
prints something unusable gives a null field and an `unavailable_sources`
entry; it never stops the command.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from byte_census import runner
from byte_census.checks.disk_map_reconcile import DfFormatError, parse_df
from byte_census.checks.docker_sizes import parse_docker_size
from byte_census.model import UnavailableSource

Run = Callable[[Sequence[str]], runner.RunResult]
SYSTEM_DF = ("df", "-k", "/")
DISKUTIL = ("diskutil", "info", "/")
TMUTIL = ("tmutil", "listlocalsnapshots", "/")
DOCKER_DF = ("docker", "system", "df", "--format", "{{json .}}")
DISKUTIL_FIELDS = (
    ("Volume Name", "volume_name"),
    ("File System Personality", "file_system_personality"),
    ("Container Total Space", "container_total_space"),
    ("Container Free Space", "container_free_space"),
)
SNAPSHOT_MARK = "com.apple"
DAEMON_DOWN = "Cannot connect to the Docker daemon"


class Unusable(ValueError):
    """A source answered, but its output cannot be read."""


@dataclass(frozen=True)
class Answer:
    """One optional source: its output, or why there is none."""

    source: str
    stdout: str | None
    problem: UnavailableSource | None
    stdout_bytes: int = 0


def ask(run: Run, argv: tuple[str, ...], source: str) -> Answer:
    """Run one allowlisted command; failures become an UnavailableSource."""
    command = " ".join(argv)
    try:
        result = run(argv)
    except runner.RejectedArgvError:
        raise
    except runner.RunnerError as error:
        reason = error.reason if error.reason != "rejected" else "failed"
        return Answer(source, None, UnavailableSource(source, reason, str(error)))
    if result.ok:
        return Answer(source, result.stdout, None, result.stdout_bytes)
    stderr = result.stderr.strip()[:200]
    reason = "not_running" if DAEMON_DOWN in stderr else "failed"
    detail = f"`{command}` exited with status {result.returncode}: {stderr}"
    return Answer(
        source, None, UnavailableSource(source, reason, detail), result.stdout_bytes
    )


def parse_diskutil(stdout: str) -> dict[str, str | None]:
    """The four retained `diskutil info /` fields, values kept as strings."""
    found: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            found.setdefault(key.strip(), value.strip())
    values = {name: found.get(key) for key, name in DISKUTIL_FIELDS}
    if all(value is None for value in values.values()):
        raise Unusable("`diskutil info /` printed none of the expected fields")
    return values


def count_snapshots(stdout: str) -> int:
    """Lines naming a local snapshot (`com.apple...`), as storage-inventory.sh."""
    return sum(1 for line in stdout.splitlines() if SNAPSHOT_MARK in line)


def docker_reported_size(stdout: str) -> int:
    """Sum of the `Size` column of `docker system df --format {{json .}}`."""
    total = 0
    rows = [line for line in stdout.splitlines() if line.strip()]
    if not rows:
        raise Unusable("`docker system df` printed no rows")
    for line in rows:
        try:
            row = json.loads(line)
        except (ValueError, RecursionError) as error:
            raise Unusable("a `docker system df` line is not JSON") from error
        size = (
            parse_docker_size(str(row.get("Size", "")))
            if isinstance(row, dict)
            else None
        )
        if size is None:
            raise Unusable("a `docker system df` row has no readable Size")
        total += size
    return total


def _system_df(stdout: str) -> dict[str, Any]:
    try:
        usage = parse_df(stdout, "/")
    except DfFormatError as error:
        raise Unusable(f"`df -k /` output is not usable: {error}") from error
    return {"mount": "/", "used_bytes": usage.used_bytes}


def _docker(answer: Answer) -> dict[str, Any]:
    size = docker_reported_size(answer.stdout) if answer.stdout is not None else None
    return {
        "available": size is not None,
        "docker_reported_size_bytes": size,
        "summed_into_host_totals": False,
        "see_check": "docker scan",
    }


SOURCES: tuple[tuple[str, str, tuple[str, ...], Callable[[str], Any]], ...] = (
    ("df_system_volume", "df_system_volume", SYSTEM_DF, _system_df),
    ("diskutil", "diskutil", DISKUTIL, parse_diskutil),
    ("local_snapshot_count", "tmutil", TMUTIL, count_snapshots),
)


@dataclass(frozen=True)
class SystemContext:
    """`data.system` fields after `df_data_volume`, and what the calls cost."""

    fields: tuple[tuple[str, Any], ...]
    unavailable: tuple[UnavailableSource, ...]
    stdout_sizes: tuple[int, ...]


def _read(
    answer: Answer, parse: Callable[[str], Any]
) -> tuple[Any, UnavailableSource | None]:
    if answer.stdout is None:
        return None, answer.problem
    try:
        return parse(answer.stdout), None
    except Unusable as error:
        return None, UnavailableSource(answer.source, "failed", str(error))


def read_system(run: Run) -> SystemContext:
    """Ask every optional system source once, in contract field order."""
    fields: list[tuple[str, Any]] = []
    problems: list[UnavailableSource] = []
    sizes: list[int] = []
    for name, source, argv, parse in SOURCES:
        answer = ask(run, argv, source)
        value, problem = _read(answer, parse)
        fields.append((name, value))
        problems.extend([problem] if problem else [])
        sizes.append(answer.stdout_bytes)
    answer = ask(run, DOCKER_DF, "docker")
    try:
        docker = _docker(answer)
    except Unusable as error:
        answer = Answer(
            "docker", None, UnavailableSource("docker", "failed", str(error))
        )
        docker = _docker(answer)
    fields.append(("docker_informational", docker))
    problems.extend([answer.problem] if answer.problem else [])
    sizes.append(answer.stdout_bytes)
    return SystemContext(tuple(fields), tuple(problems), tuple(sizes))
