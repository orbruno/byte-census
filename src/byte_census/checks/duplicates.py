"""`byte-census duplicates scan PATH` (WI-DUPLICATES).

Finds files with identical content while reading as little as possible:
size, then a partial SHA-256, then a full SHA-256 for partial matches
(duplicates_groups). Hard links form one copy and never count as waste.
`reclaimable_estimate_bytes` is the allocated size of every copy except the
one the suggestion keeps, and always carries the clone caveat.
"""

from typing import Any

import click

from byte_census import fsread
from byte_census.checks.duplicates_collect import (
    LEFT,
    RIGHT,
    Inode,
    RootSpec,
    collect,
)
from byte_census.checks.duplicates_groups import Group, find_groups
from byte_census.command import CheckResult, format_option, run_observation
from byte_census.cost import CostCounters
from byte_census.errors import usage_error
from byte_census.model import (
    Data,
    Finding,
    Scope,
    ScopeRoot,
    finding_id,
    order_findings_by_size,
)
from byte_census.paths import validate_root
from byte_census.suggestions import build_duplicate_suggestion

COMMAND = "duplicates scan"
KIND = "duplicate_group"
CLONE = "apfs_clone_or_shared_extent"
HARD_LINKS = "hard_links_merged"
SPARSE = "sparse_file"


def _caveats(members: tuple[Inode, ...]) -> tuple[str, ...]:
    found = {CLONE}
    if any(len(member.names) > 1 for member in members):
        found.add(HARD_LINKS)
    if any(member.size > member.allocated for member in members):
        found.add(SPARSE)
    return tuple(sorted(found))


def _file(member: Inode) -> dict[str, Any]:
    return {
        "path": member.primary,
        "allocated_bytes": member.allocated,
        "hard_link_paths": list(member.other_names),
    }


def _removals(members: tuple[Inode, ...]) -> tuple[str, ...]:
    return tuple(
        name for member in members[1:] for name in (member.primary, *member.other_names)
    )


def group_finding(group: Group) -> tuple[Finding, Any]:
    """The finding for one group and its per-finding suggestion."""
    members = group.members
    target = f"sha256:{group.content_sha256}"
    fid = finding_id("dup", KIND, target)
    suggestion = build_duplicate_suggestion(fid, members[0].primary, _removals(members))
    finding = Finding(
        id=fid,
        kind=KIND,
        target=target,
        logical_bytes=sum(member.size for member in members),
        allocated_bytes=sum(member.allocated for member in members),
        reclaimable_estimate_bytes=sum(member.allocated for member in members[1:]),
        caveats=_caveats(members),
        suggestion_ids=(suggestion.id,),
        details={
            "content_sha256": group.content_sha256,
            "partial_sha256": group.partial_sha256,
            "file_logical_bytes": members[0].size,
            "copy_count": len(members),
            "files": [_file(member) for member in members],
        },
    )
    return finding, suggestion


def _scope_root(given: str) -> ScopeRoot:
    resolved = str(validate_root(given))
    return ScopeRoot(resolved, given, fsread.lstat(resolved).st_dev)


def duplicates_check(
    path: str, compare: str | None, min_size: int, recursive: bool
) -> CheckResult:
    """Collect, hash in stages, and build the observation."""
    roots = (_scope_root(path),)
    specs = (RootSpec(roots[0].path, LEFT),)
    if compare is not None:
        roots += (_scope_root(compare),)
        specs += (RootSpec(roots[1].path, RIGHT),)
    collection = collect(specs, recursive, min_size)
    outcome = find_groups(collection.inodes, compare is not None)
    pairs = tuple(group_finding(group) for group in outcome.groups)
    findings = order_findings_by_size(finding for finding, _ in pairs)
    summary = {
        "files_considered": len(collection.inodes),
        "size_candidates": outcome.size_candidates,
        "partial_hash_candidates": outcome.partial_hash_candidates,
        "duplicate_groups": len(findings),
        "duplicate_copies": sum(len(group.members) for group in outcome.groups),
        "reclaimable_estimate_bytes": sum(
            finding.reclaimable_estimate_bytes or 0 for finding in findings
        ),
    }
    options = {
        "compare": roots[1].path if compare is not None else None,
        "min_size": min_size,
        "recursive": recursive,
    }
    counters = (
        CostCounters()
        .add_entries(collection.entries_visited)
        .add_content_bytes(outcome.bytes_read)
    )
    return CheckResult(
        data=Data(summary, findings, tuple(s for _, s in pairs)),
        scope=Scope(roots, options, collection.skipped_mounts),
        counters=counters,
        incomplete_coverage=collection.coverage + outcome.coverage,
    )


class DuplicatesGroup(click.Group):
    """Reports Click errors raised without a context against the subcommand."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except click.UsageError as error:
            if error.ctx is not None:
                raise
            path = ctx.command_path
            if ctx.invoked_subcommand is not None:
                path = f"{path} {ctx.invoked_subcommand}"
            raise usage_error(path, error.format_message()) from error


@click.group("duplicates", cls=DuplicatesGroup)
def duplicates() -> None:
    """
    Find files with identical content.

    Example:

      \b
      byte-census duplicates scan ~/Downloads
    """


@duplicates.command("scan")
@click.argument("path")
@click.option(
    "--compare",
    default=None,
    metavar="PATH",
    help="Report only content found both under PATH and under this directory.",
)
@click.option(
    "--min-size",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help="Ignore files smaller than this many bytes. Empty files are always ignored.",
)
@click.option(
    "--recursive/--no-recursive",
    default=True,
    show_default=True,
    help="Descend into subdirectories.",
)
@format_option
@click.pass_context
def scan(
    ctx: click.Context,
    path: str,
    compare: str | None,
    min_size: int,
    recursive: bool,
    output_format: str,
) -> None:
    """
    Find duplicate files under PATH, reading as little content as possible.

    Files are grouped by size, then by a SHA-256 of their first 64 KiB, then
    by a full SHA-256. Hard links count as one copy. Nothing is deleted;
    suggestions are text only and need the owner's authorization.

    Example:

      \b
      # Duplicates of at least 1 MiB in Downloads
      byte-census duplicates scan ~/Downloads --min-size 1048576
      \b
      # Content present both in Downloads and in an archive
      byte-census duplicates scan ~/Downloads --compare /Volumes/Archive
    """
    run_observation(
        ctx,
        COMMAND,
        output_format,
        lambda: duplicates_check(path, compare, min_size, recursive),
    )
