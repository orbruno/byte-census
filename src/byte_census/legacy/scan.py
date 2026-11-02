"""Directory scanning and duplicate detection for the legacy dupfind command."""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from rich.progress import track

from byte_census import fsread
from byte_census.legacy.consoles import status_console
from byte_census.legacy.hashing import calculate_hash


def collect_files(path: Path, recursive: bool = True, min_size: int = 0) -> list[Path]:
    """Collect regular files under path; see collect_files_with_errors."""
    return collect_files_with_errors(path, recursive, min_size)[0]


def _walk_items(path: Path, recursive: bool) -> Iterable[fsread.WalkItem]:
    """Enumerate through fsread: no symlinks, no other devices, no dataless dirs."""
    if recursive:
        return fsread.walk(path)
    return fsread.list_directory(path)


def collect_files_with_errors(
    path: Path, recursive: bool = True, min_size: int = 0
) -> tuple[list[Path], list[str]]:
    """
    Collect regular files from a path and the enumeration problems seen.

    Directories are listed only through fsread, so symlinks are never followed,
    other volumes are not entered, and dataless directories are never listed.
    Those and unreadable directories are returned as warning messages.

    Args:
        path: Directory (or single file) path to scan
        recursive: Whether to search recursively
        min_size: Minimum file size in bytes to consider

    Returns:
        Tuple of (sorted file paths, warning messages)
    """
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    if path.is_symlink():
        return [], []

    if path.is_file():
        return ([path] if path.stat().st_size >= min_size else []), []

    files: list[Path] = []
    errors: list[str] = []
    for item in _walk_items(path, recursive):
        if isinstance(item, fsread.WalkError):
            errors.append(f"Cannot list {item.path}: {item.reason}")
        elif (
            isinstance(item, fsread.WalkEntry)
            and item.kind == "file"
            and item.stat.st_size >= min_size
        ):
            files.append(Path(item.path))
    return sorted(files), errors


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
    files, walk_errors = collect_files_with_errors(path, recursive, min_size)

    if not files:
        return {}, walk_errors, 0

    size_groups, errors = group_files_by_size(files)
    errors = walk_errors + errors
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
    files1, walk_errors1 = collect_files_with_errors(path1, recursive, min_size)
    files2, walk_errors2 = collect_files_with_errors(path2, recursive, min_size)
    size_groups1, errors1 = group_files_by_size(files1)
    size_groups2, errors2 = group_files_by_size(files2)
    errors = walk_errors1 + walk_errors2 + errors1 + errors2

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
