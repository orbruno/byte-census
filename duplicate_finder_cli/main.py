"""Main CLI implementation for duplicate file finder."""

import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

import click
from rich.console import Console
from rich.progress import track

console = Console()
status_console = Console(stderr=True)


class DuplicateStats(TypedDict):
    files_scanned: int
    duplicate_groups: int
    duplicate_files: int
    wasted_bytes: int
    wasted_human: str


def calculate_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Calculate cryptographic hash of a file using chunked reading.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        Hexadecimal hash string

    Raises:
        IOError: If file cannot be read
    """
    hash_func = hashlib.new(algorithm)

    try:
        with open(file_path, "rb") as f:
            # Read in 8KB chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(8192), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except (IOError, PermissionError) as e:
        raise IOError(f"Cannot read file {file_path}: {e}")


def collect_files(path: Path, recursive: bool = True, min_size: int = 0) -> list[Path]:
    """
    Collect all files from a directory.

    Args:
        path: Directory path to scan
        recursive: Whether to search recursively
        min_size: Minimum file size in bytes to consider

    Returns:
        List of file paths
    """
    files = []

    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    if path.is_symlink():
        return []

    if path.is_file():
        # Single file provided
        if path.stat().st_size >= min_size:
            return [path]
        return []

    # Directory scanning
    pattern = "**/*" if recursive else "*"

    for item in path.glob(pattern):
        # Skip directories and symlinks
        if item.is_file() and not item.is_symlink():
            try:
                if item.stat().st_size >= min_size:
                    files.append(item)
            except (OSError, PermissionError):
                # Skip files we can't stat
                continue

    return sorted(files)


def group_files_by_size(files: list[Path]) -> tuple[dict[int, list[Path]], list[str]]:
    """Group readable files by size before content hashing."""
    size_groups: defaultdict[int, list[Path]] = defaultdict(list)
    errors: list[str] = []

    for file_path in files:
        try:
            size_groups[file_path.stat().st_size].append(file_path)
        except OSError as error:
            errors.append(f"Cannot stat file {file_path}: {error}")

    return dict(size_groups), errors


def find_duplicates_single(
    path: Path,
    recursive: bool = True,
    min_size: int = 0,
    quiet: bool = False,
) -> tuple[dict[str, list[Path]], list[str], int]:
    """
    Find duplicate files within a single directory.

    Args:
        path: Directory path to scan
        recursive: Search recursively
        min_size: Minimum file size to consider
        quiet: Suppress progress output

    Returns:
        Tuple of (duplicates_dict, errors_list, files_scanned)
        duplicates_dict: {hash: [file_paths]} for files with duplicates
        errors_list: List of error messages for files that couldn't be processed
    """
    hash_map: defaultdict[str, list[Path]] = defaultdict(list)

    # Collect files
    files = collect_files(path, recursive, min_size)

    if not files:
        return {}, [], 0

    size_groups, errors = group_files_by_size(files)
    candidates = sorted(
        file_path
        for same_size_files in size_groups.values()
        if len(same_size_files) > 1
        for file_path in same_size_files
    )

    file_iterator = (
        track(candidates, description="Hashing files...", console=status_console)
        if not quiet
        else candidates
    )

    for file_path in file_iterator:
        try:
            file_hash = calculate_hash(file_path)
            hash_map[file_hash].append(file_path)
        except IOError as e:
            errors.append(str(e))
            continue

    # Filter to only duplicates (hashes with >1 file)
    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}

    return duplicates, errors, len(files)


def find_duplicates_compare(
    path1: Path,
    path2: Path,
    recursive: bool = True,
    min_size: int = 0,
    quiet: bool = False,
) -> tuple[dict[str, list[Path]], list[str], int]:
    """
    Find duplicate files between two directories.

    Args:
        path1: First directory path
        path2: Second directory path
        recursive: Search recursively
        min_size: Minimum file size to consider
        quiet: Suppress progress output

    Returns:
        Tuple of (duplicates_dict, errors_list, files_scanned)
        duplicates_dict: {hash: [all_matching_files]} (flattened from both dirs)
        errors_list: List of error messages
    """
    hash_map1: defaultdict[str, list[Path]] = defaultdict(list)
    hash_map2: defaultdict[str, list[Path]] = defaultdict(list)
    files1 = collect_files(path1, recursive, min_size)
    files2 = collect_files(path2, recursive, min_size)
    size_groups1, errors1 = group_files_by_size(files1)
    size_groups2, errors2 = group_files_by_size(files2)
    errors = errors1 + errors2

    common_sizes = set(size_groups1) & set(size_groups2)
    candidates1 = sorted(
        file_path for size in common_sizes for file_path in size_groups1[size]
    )
    candidates2 = sorted(
        file_path for size in common_sizes for file_path in size_groups2[size]
    )

    if not quiet:
        status_console.print(
            f"Hashing {len(candidates1)} candidate files from {path1}...",
            style="cyan",
            markup=False,
        )

    for file_path in (
        track(
            candidates1,
            description="Hashing directory 1...",
            console=status_console,
        )
        if not quiet
        else candidates1
    ):
        try:
            file_hash = calculate_hash(file_path)
            hash_map1[file_hash].append(file_path)
        except IOError as e:
            errors.append(str(e))

    if not quiet:
        status_console.print(
            f"Hashing {len(candidates2)} candidate files from {path2}...",
            style="cyan",
            markup=False,
        )

    for file_path in (
        track(
            candidates2,
            description="Hashing directory 2...",
            console=status_console,
        )
        if not quiet
        else candidates2
    ):
        try:
            file_hash = calculate_hash(file_path)
            hash_map2[file_hash].append(file_path)
        except IOError as e:
            errors.append(str(e))

    common_hashes = sorted(set(hash_map1) & set(hash_map2))

    duplicates = {
        file_hash: hash_map1[file_hash] + hash_map2[file_hash]
        for file_hash in common_hashes
    }

    return duplicates, errors, len(files1) + len(files2)


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


@click.command()
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

    Examples:

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

        output_text: str | None = None
        if output_format == "table":
            if output:
                output_text = format_table_text(duplicates, stats)
            else:
                format_table_output(duplicates, stats)
        elif output_format == "json":
            output_text = format_json_output(duplicates, stats)
        elif output_format == "csv":
            output_text = format_csv_output(duplicates)

        if output:
            try:
                output.write_text(output_text or "", encoding="utf-8")
            except OSError as error:
                raise click.ClickException(
                    f"Cannot write output file {output}: {error}"
                ) from error
            status_console.print(
                f"✓ Results saved to {output}", style="green", markup=False
            )
        elif output_text is not None:
            click.echo(output_text, nl=not output_text.endswith("\n"))

        if errors:
            status_console.print(
                f"\n⚠ Encountered {len(errors)} errors:", style="yellow", markup=False
            )
            for error in errors[:10]:
                status_console.print(f"  {error}", markup=False)
            if len(errors) > 10:
                status_console.print(f"  ... and {len(errors) - 10} more", markup=False)

    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e


def cli() -> None:
    """Entry point for the CLI."""
    find()


if __name__ == "__main__":
    cli()
