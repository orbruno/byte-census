"""Reconciliation of `disk map` against `df -k /System/Volumes/Data`.

`df` is the one required source: when it cannot run, exits nonzero, or prints
nothing parseable, the command exits 4 (envelope.md, Exit codes). The delta
is signed, df used minus measured; a negative delta is an overcount and is
never clamped to zero.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from byte_census import runner
from byte_census.errors import SourceUnavailableError

DATA_MOUNT = "/System/Volumes/Data"
DF_ARGV = ("df", "-k", DATA_MOUNT)
DF_COMMAND = " ".join(DF_ARGV)
KIB = 1024
NOTE = (
    "Measured is the sum of unique counted contributions in precedence order. "
    "Signed delta: df used minus measured; negative means overcount and is "
    "never clamped."
)
BASE_HEADER = ("Filesystem", "1024-blocks", "Used", "Available", "Capacity")
HEADERS = (
    (*BASE_HEADER, "Mounted", "on"),
    (*BASE_HEADER, "iused", "ifree", "%iused", "Mounted", "on"),
)
PERCENT_COLUMNS = frozenset({"Capacity", "%iused"})
DIGITS = re.compile(r"[0-9]+")
PERCENT = re.compile(r"[0-9]+%")
DfRunner = Callable[[Sequence[str]], runner.RunResult]


@dataclass(frozen=True)
class DfUsage:
    """`df -k` columns converted to bytes, and the captured stdout size."""

    total_bytes: int
    used_bytes: int
    available_bytes: int
    stdout_bytes: int = 0
    mount: str = DATA_MOUNT

    def to_dict(self) -> dict[str, Any]:
        return {
            "mount": self.mount,
            "total_bytes": self.total_bytes,
            "used_bytes": self.used_bytes,
            "available_bytes": self.available_bytes,
        }


class DfFormatError(ValueError):
    """`df -k` output that is not exactly one header and one row for the mount."""


def _unavailable(reason: str) -> SourceUnavailableError:
    return SourceUnavailableError(
        error=f"disk map could not read data-volume usage with `{DF_COMMAND}`",
        reason=reason,
        suggestion="Check that /bin/df runs on this Mac, then run "
        "`byte-census disk map` again.",
    )


def _columns(header: str) -> tuple[str, ...]:
    """Data column names between `Filesystem` and `Mounted on`."""
    names = tuple(header.split())
    if names not in HEADERS:
        raise DfFormatError(f"unexpected df header: {header.strip()!r}")
    return names[1:-2]


def _row_values(row: str, mount: str, count: int) -> tuple[str, ...]:
    """The `count` columns before the mount; the filesystem name keeps spaces."""
    stripped = row.rstrip()
    if not stripped.endswith(mount) or not stripped[: -len(mount)][-1:].isspace():
        raise DfFormatError(f"df row is not for {mount}: {row.strip()!r}")
    tokens = stripped[: -len(mount)].split()
    if len(tokens) < count + 1:
        raise DfFormatError(f"df row has too few columns: {row.strip()!r}")
    return tuple(tokens[-count:])


def parse_df(stdout: str, mount: str = DATA_MOUNT) -> DfUsage:
    """Parse `df -k MOUNT`: exactly one known header and one row for MOUNT.

    Columns are read by position from the header, counted back from the
    mount point, so a filesystem name with spaces or digits cannot shift
    them. Raises DfFormatError for anything else (512-blocks, extra lines,
    another mount, malformed numbers).
    """
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        raise DfFormatError(f"df printed {len(lines)} lines, expected 2")
    columns = _columns(lines[0])
    values = dict(zip(columns, _row_values(lines[1], mount, len(columns)), strict=True))
    for name, value in values.items():
        pattern = PERCENT if name in PERCENT_COLUMNS else DIGITS
        if not pattern.fullmatch(value):
            raise DfFormatError(f"df column {name} is not valid: {value!r}")
    total, used, available = (
        int(values[name]) * KIB for name in ("1024-blocks", "Used", "Available")
    )
    return DfUsage(total, used, available, mount=mount)


def read_df(run: DfRunner) -> DfUsage:
    """Run `df -k /System/Volumes/Data`; any failure raises exit 4."""
    try:
        result = run(DF_ARGV)
    except runner.RejectedArgvError:
        raise
    except runner.RunnerError as error:
        raise _unavailable(str(error)) from error
    if not result.ok:
        detail = result.stderr.strip()[:200]
        raise _unavailable(
            f"`{DF_COMMAND}` exited with status {result.returncode}: {detail}"
        )
    try:
        usage = parse_df(result.stdout)
    except DfFormatError as error:
        raise _unavailable(f"`{DF_COMMAND}` output is not usable: {error}") from error
    return replace(usage, stdout_bytes=result.stdout_bytes)


@dataclass(frozen=True)
class Contribution:
    """One reconciliation unit: a finding and its counted contribution."""

    finding_id: str
    counted_allocated_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "counted_allocated_bytes": self.counted_allocated_bytes,
        }


def reconciliation(
    usage: DfUsage, contributions: Sequence[Contribution]
) -> dict[str, Any]:
    """The `data.reconciliation` section; contributions in precedence order."""
    measured = sum(c.counted_allocated_bytes for c in contributions)
    delta = usage.used_bytes - measured
    return {
        "df_command": DF_COMMAND,
        "df_used_bytes": usage.used_bytes,
        "measured_allocated_bytes": measured,
        "delta_bytes": delta,
        "overcount": delta < 0,
        "contributions": [c.to_dict() for c in contributions],
        "note": NOTE,
    }
