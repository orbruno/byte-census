"""Reconciliation of `disk map` against `df -k /System/Volumes/Data`.

`df` is the one required source: when it cannot run, exits nonzero, or prints
nothing parseable, the command exits 4 (envelope.md, Exit codes). The delta
is signed, df used minus measured; a negative delta is an overcount and is
never clamped to zero.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
DfRunner = Callable[[Sequence[str]], runner.RunResult]


@dataclass(frozen=True)
class DfUsage:
    """`df -k` columns converted to bytes, and the captured stdout size."""

    total_bytes: int
    used_bytes: int
    available_bytes: int
    stdout_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "mount": DATA_MOUNT,
            "total_bytes": self.total_bytes,
            "used_bytes": self.used_bytes,
            "available_bytes": self.available_bytes,
        }


def _unavailable(reason: str) -> SourceUnavailableError:
    return SourceUnavailableError(
        error=f"disk map could not read data-volume usage with `{DF_COMMAND}`",
        reason=reason,
        suggestion="Check that /bin/df runs on this Mac, then run "
        "`byte-census disk map` again.",
    )


def parse_df(stdout: str) -> DfUsage:
    """Read 1024-blocks, Used, and Available from the last `df -k` line.

    The filesystem name may contain spaces, so the columns are the first
    three consecutive integers on the line.
    """
    lines = [line for line in stdout.splitlines() if line.strip()]
    tokens = lines[-1].split() if len(lines) >= 2 else []
    for index in range(len(tokens) - 2):
        window = tokens[index : index + 3]
        if all(token.isdigit() for token in window):
            total, used, available = (int(token) * KIB for token in window)
            return DfUsage(total, used, available)
    raise _unavailable(f"`{DF_COMMAND}` printed no usage line: {stdout[:200]!r}")


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
    usage = parse_df(result.stdout)
    return DfUsage(
        usage.total_bytes, usage.used_bytes, usage.available_bytes, result.stdout_bytes
    )


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
