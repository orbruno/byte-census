"""dupfind command: v1 duplicate file finder."""

from pathlib import Path

import click

from byte_census.legacy.consoles import console, status_console
from byte_census.legacy.formatting import (
    DuplicateStats,
    calculate_statistics,
    format_csv_output,
    format_json_output,
    format_table_output,
    format_table_text,
)
from byte_census.legacy.report_writer import write_report
from byte_census.legacy.scan import find_duplicates_compare, find_duplicates_single

DEPRECATION_NOTICE = (
    "dupfind is deprecated; use 'byte-census duplicates scan'. "
    "It will be removed in 3.0.0."
)

EXAMPLES = """\
Example:

\b
  # Find duplicates in current directory
  dupfind .

\b
  # Find duplicates in Downloads (non-recursive)
  dupfind ~/Downloads --no-recursive

\b
  # Compare two directories
  dupfind /path/dir1 --compare /path/dir2

\b
  # Output as JSON to file
  dupfind /path --format json --output results.json

\b
  # Ignore files smaller than 1MB
  dupfind /path --min-size 1048576
"""


@click.command(
    context_settings={"help_option_names": ["--help", "-h"]},
    epilog=EXAMPLES,
)
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--compare",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Compare with another directory to find duplicates between them",
)
@click.option(
    "--recursive/--no-recursive",
    "-r/-R",
    default=True,
    help="Search recursively in subdirectories (default: recursive)",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json", "csv"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Save results to file instead of stdout",
)
@click.option(
    "--min-size",
    type=click.IntRange(min=0),
    default=0,
    help="Minimum file size in bytes to consider (default: 0)",
)
@click.option(
    "--quiet", "-q", is_flag=True, help="Suppress progress output, only show results"
)
def find(
    path: Path,
    compare: Path | None,
    recursive: bool,
    output_format: str,
    output: Path | None,
    min_size: int,
    quiet: bool,
) -> None:
    """
    Find duplicate files using cryptographic hashing.

    PATH is the directory to scan for duplicates.
    """
    click.echo(DEPRECATION_NOTICE, err=True)
    try:
        if compare:
            duplicates, errors, files_scanned = find_duplicates_compare(
                path, compare, recursive, min_size, quiet
            )
        else:
            duplicates, errors, files_scanned = find_duplicates_single(
                path, recursive, min_size, quiet
            )

        stats = calculate_statistics(duplicates, files_scanned)
        output_text = _render(duplicates, stats, output_format, output)

        if output:
            write_report(output, output_text)
        elif output_text is not None:
            click.echo(output_text, nl=not output_text.endswith("\n"))

        _report_errors(errors)

    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e


def _render(
    duplicates: dict[str, list[Path]],
    stats: DuplicateStats,
    output_format: str,
    output: Path | None,
) -> str | None:
    """Render results; table output to stdout is printed directly and returns None."""
    if output_format == "table":
        if output:
            return format_table_text(duplicates, stats)
        format_table_output(duplicates, stats, console)
        return None
    if output_format == "json":
        return format_json_output(duplicates, stats)
    return format_csv_output(duplicates)


def _report_errors(errors: list[str]) -> None:
    """Print up to ten collected errors to stderr."""
    if not errors:
        return
    status_console.print(
        f"\n⚠ Encountered {len(errors)} errors:", style="yellow", markup=False
    )
    for error in errors[:10]:
        status_console.print(f"  {error}", markup=False)
    if len(errors) > 10:
        status_console.print(f"  ... and {len(errors) - 10} more", markup=False)


def cli() -> None:
    """Entry point for the CLI."""
    find()


if __name__ == "__main__":
    cli()
