"""Click commands `byte-census disk` and `byte-census disk map`."""

from typing import Any

import click

from byte_census.checks import disk_map
from byte_census.command import format_option, run_observation
from byte_census.errors import usage_error

COMMAND = "disk map"


class DiskGroup(click.Group):
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


@click.group("disk", cls=DiskGroup)
def disk() -> None:
    """
    Map where the data volume's used space is.

    Example:

      \b
      byte-census disk map --scan-root ~/Library
    """


@disk.command("map")
@click.option(
    "--scan-root",
    "scan_roots",
    multiple=True,
    required=True,
    metavar="PATH",
    help="Folder on the data volume to measure. Repeat for several roots.",
)
@click.option(
    "--top",
    type=click.IntRange(min=1),
    default=disk_map.DEFAULT_TOP,
    show_default=True,
    help="Show this many largest first-level folders per root; totals cover all.",
)
@click.option(
    "--large-file-min",
    "large_file_min_mb",
    type=click.IntRange(min=0),
    default=disk_map.DEFAULT_LARGE_FILE_MIN_MB,
    show_default=True,
    metavar="MB",
    help="List files larger than this many MiB (20 largest per root).",
)
@format_option
@click.pass_context
def map_command(
    ctx: click.Context,
    scan_roots: tuple[str, ...],
    top: int,
    large_file_min_mb: int,
    output_format: str,
) -> None:
    """
    Measure each scan root on the data volume, its largest first-level
    folders and large files, and reconcile the total with
    `df -k /System/Volumes/Data`. Nested and repeated roots are shown but
    counted once; hard links are counted once. Read-only; it never suggests
    or deletes anything.

    Example:

      \b
      # Two roots, ten folders each
      byte-census disk map --scan-root ~/Library --scan-root ~/Documents --top 10
      \b
      # Files over 1 GiB, as a table
      byte-census disk map --scan-root ~ --large-file-min 1024 --format table
    """
    options = disk_map.Options(top=top, large_file_min_mb=large_file_min_mb)
    run_observation(
        ctx,
        COMMAND,
        output_format,
        lambda: disk_map.disk_map(disk_map.default_environment(), scan_roots, options),
    )
