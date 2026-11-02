"""Directory scanning and duplicate detection for the legacy dupfind command."""

from collections import defaultdict
from pathlib import Path

from rich.progress import track

from byte_census.legacy.consoles import status_console
from byte_census.legacy.hashing import calculate_hash


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


def _repeated_size_candidates(size_groups: dict[int, list[Path]]) -> list[Path]:
    """Return sorted files whose size is shared with at least one other file."""
    return sorted(
        file_path
        for same_size_files in size_groups.values()
        if len(same_size_files) > 1
        for file_path in same_size_files
    )


def _common_size_candidates(
    size_groups: dict[int, list[Path]], common_sizes: set[int]
) -> list[Path]:
    """Return sorted files from one directory whose size appears in both."""
    return sorted(file_path for size in common_sizes for file_path in size_groups[size])


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
    files = collect_files(path, recursive, min_size)

    if not files:
        return {}, [], 0

    size_groups, errors = group_files_by_size(files)
    candidates = _repeated_size_candidates(size_groups)

    file_iterator = (
        track(candidates, description="Hashing files...", console=status_console)
        if not quiet
        else candidates
    )

    hash_map: defaultdict[str, list[Path]] = defaultdict(list)
    for file_path in file_iterator:
        try:
            hash_map[calculate_hash(file_path)].append(file_path)
        except OSError as e:
            errors.append(str(e))

    # Filter to only duplicates (hashes with >1 file)
    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}

    return duplicates, errors, len(files)


def _hash_candidates(
    candidates: list[Path],
    source: Path,
    description: str,
    quiet: bool,
) -> tuple[defaultdict[str, list[Path]], list[str]]:
    """Hash candidate files, announcing progress unless quiet."""
    hash_map: defaultdict[str, list[Path]] = defaultdict(list)
    errors: list[str] = []

    if not quiet:
        status_console.print(
            f"Hashing {len(candidates)} candidate files from {source}...",
            style="cyan",
            markup=False,
        )

    file_iterator = (
        track(candidates, description=description, console=status_console)
        if not quiet
        else candidates
    )
    for file_path in file_iterator:
        try:
            hash_map[calculate_hash(file_path)].append(file_path)
        except OSError as e:
            errors.append(str(e))

    return hash_map, errors


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
    files1 = collect_files(path1, recursive, min_size)
    files2 = collect_files(path2, recursive, min_size)
    size_groups1, errors1 = group_files_by_size(files1)
    size_groups2, errors2 = group_files_by_size(files2)
    errors = errors1 + errors2

    common_sizes = set(size_groups1) & set(size_groups2)
    candidates1 = _common_size_candidates(size_groups1, common_sizes)
    candidates2 = _common_size_candidates(size_groups2, common_sizes)

    hash_map1, hash_errors1 = _hash_candidates(
        candidates1, path1, "Hashing directory 1...", quiet
    )
    hash_map2, hash_errors2 = _hash_candidates(
        candidates2, path2, "Hashing directory 2...", quiet
    )
    errors = errors + hash_errors1 + hash_errors2

    common_hashes = sorted(set(hash_map1) & set(hash_map2))

    duplicates = {
        file_hash: hash_map1[file_hash] + hash_map2[file_hash]
        for file_hash in common_hashes
    }

    return duplicates, errors, len(files1) + len(files2)
