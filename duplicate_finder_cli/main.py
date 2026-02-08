"""Main CLI implementation for duplicate file finder."""

import hashlib
import io
import json
import csv
from pathlib import Path
from collections import defaultdict
from typing import TypedDict

import click
from rich.console import Console
from rich.progress import track

console = Console()


class DuplicateStats(TypedDict):
    duplicate_groups: int
    duplicate_files: int
    wasted_bytes: int
    wasted_human: str


def calculate_hash(file_path: Path, algorithm: str = 'sha256') -> str:
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
        with open(file_path, 'rb') as f:
            # Read in 8KB chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(8192), b''):
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

    if path.is_file():
        # Single file provided
        if path.stat().st_size >= min_size:
            return [path]
        return []

    # Directory scanning
    pattern = '**/*' if recursive else '*'

    for item in path.glob(pattern):
        # Skip directories and symlinks
        if item.is_file() and not item.is_symlink():
            try:
                if item.stat().st_size >= min_size:
                    files.append(item)
            except (OSError, PermissionError):
                # Skip files we can't stat
                continue

    return files


def find_duplicates_single(
    path: Path,
    recursive: bool = True,
    min_size: int = 0,
    quiet: bool = False
) -> tuple[dict[str, list[Path]], list[str]]:
    """
    Find duplicate files within a single directory.

    Args:
        path: Directory path to scan
        recursive: Search recursively
        min_size: Minimum file size to consider
        quiet: Suppress progress output

    Returns:
        Tuple of (duplicates_dict, errors_list)
        duplicates_dict: {hash: [file_paths]} for files with duplicates
        errors_list: List of error messages for files that couldn't be processed
    """
    hash_map = defaultdict(list)
    errors = []

    # Collect files
    files = collect_files(path, recursive, min_size)

    if not files:
        return {}, []

    # Hash all files
    file_iterator = track(files, description="Hashing files...") if not quiet else files

    for file_path in file_iterator:
        try:
            file_hash = calculate_hash(file_path)
            hash_map[file_hash].append(file_path)
        except IOError as e:
            errors.append(str(e))
            continue

    # Filter to only duplicates (hashes with >1 file)
    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}

    return duplicates, errors


def find_duplicates_compare(
    path1: Path,
    path2: Path,
    recursive: bool = True,
    min_size: int = 0,
    quiet: bool = False
) -> tuple[dict[str, list[Path]], list[str]]:
    """
    Find duplicate files between two directories.

    Args:
        path1: First directory path
        path2: Second directory path
        recursive: Search recursively
        min_size: Minimum file size to consider
        quiet: Suppress progress output

    Returns:
        Tuple of (duplicates_dict, errors_list)
        duplicates_dict: {hash: [all_matching_files]} (flattened from both dirs)
        errors_list: List of error messages
    """
    hash_map1: defaultdict[str, list[Path]] = defaultdict(list)
    hash_map2: defaultdict[str, list[Path]] = defaultdict(list)
    errors: list[str] = []

    files1 = collect_files(path1, recursive, min_size)
    files2 = collect_files(path2, recursive, min_size)

    if not quiet:
        console.print(f"[cyan]Hashing {len(files1)} files from {path1}...[/cyan]")

    for file_path in (track(files1, description="Hashing directory 1...") if not quiet else files1):
        try:
            file_hash = calculate_hash(file_path)
            hash_map1[file_hash].append(file_path)
        except IOError as e:
            errors.append(str(e))

    if not quiet:
        console.print(f"[cyan]Hashing {len(files2)} files from {path2}...[/cyan]")

    for file_path in (track(files2, description="Hashing directory 2...") if not quiet else files2):
        try:
            file_hash = calculate_hash(file_path)
            hash_map2[file_hash].append(file_path)
        except IOError as e:
            errors.append(str(e))

    common_hashes = set(hash_map1.keys()) & set(hash_map2.keys())

    duplicates = {
        h: hash_map1[h] + hash_map2[h]
        for h in common_hashes
    }

    return duplicates, errors


def calculate_statistics(duplicates: dict[str, list[Path]]) -> DuplicateStats:
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
        'duplicate_groups': total_groups,
        'duplicate_files': total_files,
        'wasted_bytes': wasted_bytes,
        'wasted_human': format_bytes(wasted_bytes),
    }


def format_table_output(duplicates: dict[str, list[Path]], stats: DuplicateStats) -> None:
    """Display duplicates in rich table format."""
    if not duplicates:
        console.print("[green]✓ No duplicates found![/green]")
        return

    console.print(f"\n[bold cyan]Found {stats['duplicate_groups']} duplicate groups "
                  f"({stats['duplicate_files']} files, {stats['wasted_human']} wasted)[/bold cyan]\n")

    for file_hash, files in duplicates.items():
        file_size = files[0].stat().st_size
        size_human = format_bytes(file_size)

        console.print(f"[yellow]Hash:[/yellow] {file_hash[:12]}... "
                     f"[dim]({len(files)} files, {size_human} each)[/dim]")

        for file_path in files:
            console.print(f"  {file_path}")

        console.print()


def format_json_output(duplicates: dict[str, list[Path]], stats: DuplicateStats) -> str:
    """Format duplicates as JSON."""
    output: dict = {
        'summary': stats,
        'duplicates': {}
    }

    for file_hash, files in duplicates.items():
        output['duplicates'][file_hash] = {
            'count': len(files),
            'size': files[0].stat().st_size,
            'files': [str(f) for f in files]
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
    writer.writerow(['hash', 'file_count', 'size_bytes', 'file_path'])
    writer.writerows(rows)

    return output.getvalue()


def format_bytes(num_bytes: int) -> str:
    """Convert bytes to human-readable format."""
    size = float(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


@click.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--compare', '-c', type=click.Path(exists=True, path_type=Path),
              help='Compare with another directory to find duplicates between them')
@click.option('--recursive/--no-recursive', '-r/-R', default=True,
              help='Search recursively in subdirectories (default: recursive)')
@click.option('--format', '-f', 'output_format',
              type=click.Choice(['table', 'json', 'csv'], case_sensitive=False),
              default='table', help='Output format (default: table)')
@click.option('--output', '-o', type=click.Path(path_type=Path),
              help='Save results to file instead of stdout')
@click.option('--min-size', type=int, default=0,
              help='Minimum file size in bytes to consider (default: 0)')
@click.option('--quiet', '-q', is_flag=True,
              help='Suppress progress output, only show results')
def find(
    path: Path,
    compare: Path | None,
    recursive: bool,
    output_format: str,
    output: Path | None,
    min_size: int,
    quiet: bool
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
            duplicates, errors = find_duplicates_compare(
                path, compare, recursive, min_size, quiet
            )
        else:
            duplicates, errors = find_duplicates_single(
                path, recursive, min_size, quiet
            )

        stats = calculate_statistics(duplicates)

        output_text: str | None = None
        if output_format == 'table':
            format_table_output(duplicates, stats)
        elif output_format == 'json':
            output_text = format_json_output(duplicates, stats)
        elif output_format == 'csv':
            output_text = format_csv_output(duplicates)

        if output:
            if output_text:
                output.write_text(output_text)
                console.print(f"[green]✓ Results saved to {output}[/green]")
            else:
                console.print("[red]✗ Cannot save table format to file. Use --format json or csv[/red]")
        elif output_text:
            console.print(output_text)

        if errors and not quiet:
            console.print(f"\n[yellow]⚠ Encountered {len(errors)} errors:[/yellow]")
            for error in errors[:10]:
                console.print(f"  {error}")
            if len(errors) > 10:
                console.print(f"  ... and {len(errors) - 10} more")

    except FileNotFoundError as e:
        console.print(f"[red]✗ Error: {e}[/red]")
        raise click.Abort()


def cli() -> None:
    """Entry point for the CLI."""
    find()


if __name__ == '__main__':
    cli()
