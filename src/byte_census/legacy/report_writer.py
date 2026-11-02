"""Report file writer for the legacy dupfind command.

This is the only module that writes files.
"""

from pathlib import Path

import click

from byte_census.legacy.consoles import status_console


def write_report(output: Path, text: str | None) -> None:
    """Write the report text to the output path, overwriting any existing file."""
    try:
        output.write_text(text or "", encoding="utf-8")
    except OSError as error:
        raise click.ClickException(
            f"Cannot write output file {output}: {error}"
        ) from error
    status_console.print(f"✓ Results saved to {output}", style="green", markup=False)
