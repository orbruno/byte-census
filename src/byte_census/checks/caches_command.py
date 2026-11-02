"""Click command `byte-census caches scan`."""

import click

from byte_census.checks import caches
from byte_census.command import format_option, run_observation

COMMAND = "caches scan"


@click.group("caches")
def caches_group() -> None:
    """
    Find the largest caches.

    Example:

      \b
      byte-census caches scan --top 10
    """


@caches_group.command("scan")
@click.option(
    "--top",
    type=click.IntRange(min=1),
    default=caches.DEFAULT_TOP,
    show_default=True,
    help="Show only this many largest caches; totals cover all of them.",
)
@format_option
@click.pass_context
def scan(ctx: click.Context, top: int, output_format: str) -> None:
    """
    Report the largest folders in ~/Library/Caches and the uv, npm, and
    Homebrew caches. Read-only; it never deletes anything.

    Example:

      \b
      # The five largest caches, as a table
      byte-census caches scan --top 5 --format table
    """
    run_observation(
        ctx,
        COMMAND,
        output_format,
        lambda: caches.caches_scan(caches.default_environment(), top),
    )
