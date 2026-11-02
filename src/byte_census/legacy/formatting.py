"""Statistics and output formatting for the legacy dupfind command."""

import csv
import io
import json
from pathlib import Path
from typing import TypedDict

from rich.console import Console

from byte_census.legacy.consoles import console


class DuplicateStats(TypedDict):
    files_scanned: int
    duplicate_groups: int
    duplicate_files: int
    wasted_bytes: int
    wasted_human: str


def calculate_statistics(
    duplicates: dict[str, list[Path]], files_scanned: int = 0
) -> DuplicateStats:
    """
    Calculate statistics about duplicates.

    Args:
        duplicates: Dictionary of duplicate file groups {hash: [file_paths]}

    Returns:
        Typed statistics dictionary
    """
    total_groups = len(duplicates)
    total_files = 0
    wasted_bytes = 0

    for files in duplicates.values():
        total_files += len(files)

        if files:
            file_size = files[0].stat().st_size
            wasted_bytes += (len(files) - 1) * file_size

    return {
        "files_scanned": files_scanned,
        "duplicate_groups": total_groups,
        "duplicate_files": total_files,
        "wasted_bytes": wasted_bytes,
        "wasted_human": format_bytes(wasted_bytes),
    }


def format_table_output(
    duplicates: dict[str, list[Path]],
    stats: DuplicateStats,
    output_console: Console = console,
) -> None:
    """Display duplicates in rich table format."""
    if not duplicates:
        output_console.print("[green]✓ No duplicates found![/green]")
        return

    output_console.print(
        f"\n[bold cyan]Found {stats['duplicate_groups']} duplicate groups "
        f"({stats['duplicate_files']} files, {stats['wasted_human']} wasted)[/bold cyan]\n"
    )

    for file_hash, files in duplicates.items():
        file_size = files[0].stat().st_size
        size_human = format_bytes(file_size)

        output_console.print(
            f"[yellow]Hash:[/yellow] {file_hash[:12]}... "
            f"[dim]({len(files)} files, {size_human} each)[/dim]"
        )

        for file_path in files:
            output_console.print(f"  {file_path}", markup=False)

        output_console.print()


def format_table_text(duplicates: dict[str, list[Path]], stats: DuplicateStats) -> str:
    """Render table output as plain text for file output."""
    output = io.StringIO()
    file_console = Console(
        file=output,
        color_system=None,
        force_terminal=False,
        width=200,
    )
    format_table_output(duplicates, stats, file_console)
    return output.getvalue()


def format_json_output(duplicates: dict[str, list[Path]], stats: DuplicateStats) -> str:
    """Format duplicates as JSON."""
    output: dict = {"summary": stats, "duplicates": {}}

    for file_hash, files in duplicates.items():
        output["duplicates"][file_hash] = {
            "count": len(files),
            "size": files[0].stat().st_size,
            "files": [str(f) for f in files],
        }

    return json.dumps(output, indent=2)


def format_csv_output(duplicates: dict[str, list[Path]]) -> str:
    """Format duplicates as CSV."""
    rows = []

    for file_hash, files in duplicates.items():
        file_count = len(files)
        file_size = files[0].stat().st_size

        for file_path in files:
            rows.append([file_hash, file_count, file_size, str(file_path)])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["hash", "file_count", "size_bytes", "file_path"])
    writer.writerows(rows)

    return output.getvalue()


def format_bytes(num_bytes: int) -> str:
    """Convert bytes to human-readable format."""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"
