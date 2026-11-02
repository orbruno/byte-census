"""Internal `byte-census _selftest` command.

Hidden from `--help` and not part of the public contract. It exercises the
command scaffold end to end (validation, metadata-only walking, cost, status,
rendering, and every error path) so the scaffold is tested before any check
exists. It never runs a process and never reads file content.
"""

import click

from byte_census import fsread
from byte_census.command import CheckResult, format_option, run_observation
from byte_census.cost import CostCounters
from byte_census.model import (
    CoverageEntry,
    Data,
    Finding,
    Scope,
    ScopeRoot,
    Suggestion,
    finding_id,
)
from byte_census.paths import validate_root
from byte_census.runner import ExecutableNotFoundError

COMMAND = "_selftest"
NO_ROOT = "selftest:none"
SIMULATED_ARGV = ("docker", "system", "df", "--format", "{{json .}}")


def _maybe_fail(fail: str | None) -> None:
    if fail == "internal":
        raise RuntimeError("selftest internal failure")
    if fail == "unavailable":
        raise ExecutableNotFoundError(SIMULATED_ARGV, "docker is not installed")


def _walk(root: str) -> tuple[int, tuple[CoverageEntry, ...], tuple[str, ...]]:
    entries = 0
    coverage: list[CoverageEntry] = []
    mounts: list[str] = []
    for item in fsread.walk(root):
        if isinstance(item, fsread.WalkError):
            coverage.append(
                CoverageEntry(item.path, item.reason, item.errno_name, item.operation)
            )
            entries += 1 if item.operation == "lstat" else 0
            continue
        entries += 1
        if isinstance(item, fsread.SkippedMount):
            mounts.append(item.path)
    return entries, tuple(coverage), tuple(mounts)


def _data(target: str, entries: int) -> Data:
    fid = finding_id("tst", "selftest", target)
    sid = f"selftest-noop@{fid}"
    finding = Finding(
        id=fid,
        kind="selftest",
        target=target,
        suggestion_ids=(sid,),
        details={"entries": entries},
    )
    suggestion = Suggestion(
        id=sid,
        command="true",
        risk="low",
        reversible=True,
        reason="Internal self-test suggestion; it changes nothing.",
        finding_ids=(fid,),
    )
    summary = {"entries": entries, "findings": 1}
    return Data(summary=summary, findings=(finding,), suggestions=(suggestion,))


def selftest_check(root: str | None, partial: bool, fail: str | None) -> CheckResult:
    """Build a CheckResult from an optional metadata-only walk of root."""
    _maybe_fail(fail)
    roots: tuple[ScopeRoot, ...] = ()
    entries, coverage, mounts = 0, (), ()
    target = NO_ROOT
    if root is not None:
        resolved = str(validate_root(root))
        roots = (ScopeRoot(resolved, root, fsread.lstat(resolved).st_dev),)
        entries, coverage, mounts = _walk(resolved)
        target = resolved
    if partial:
        coverage += (
            CoverageEntry(f"{target}/vanished", "vanished", "ENOENT", "lstat"),
        )
    options = {"fail": fail, "partial": partial}
    return CheckResult(
        data=_data(target, entries),
        scope=Scope(roots=roots, options=options, skipped_mounts=mounts),
        counters=CostCounters().add_entries(entries),
        incomplete_coverage=coverage,
    )


@click.command(COMMAND, hidden=True)
@click.option("--root", default=None, help="Directory to walk (metadata only).")
@click.option("--partial", is_flag=True, help="Add a simulated coverage gap.")
@click.option(
    "--fail",
    type=click.Choice(["internal", "unavailable"]),
    default=None,
    help="Simulate an internal error (exit 1) or a missing source (exit 4).",
)
@format_option
@click.pass_context
def selftest(
    ctx: click.Context,
    root: str | None,
    partial: bool,
    fail: str | None,
    output_format: str,
) -> None:
    """
    Internal: exercise the observation scaffold. Not a public command.

    Example:

      \b
      byte-census _selftest --root /tmp --format table
    """
    run_observation(
        ctx, COMMAND, output_format, lambda: selftest_check(root, partial, fail)
    )
