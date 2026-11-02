"""File hashing for the legacy dupfind command."""

import os
from pathlib import Path
from typing import Any

from byte_census import fsread


def _beneath_resolved_root(root: Path, file_path: Path) -> tuple[str, str]:
    """Return (realpath of root, file path re-based onto it) for O_NOFOLLOW opens."""
    resolved = os.path.realpath(root)
    relative = os.path.relpath(file_path, root)
    return resolved, os.path.join(resolved, relative)


def calculate_hash(
    file_path: Path,
    algorithm: str = "sha256",
    root: Path | None = None,
    expected: Any = None,
) -> str:
    """
    Calculate cryptographic hash of a file using chunked reading.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use (default: sha256)
        root: Scan root; when given, every component below its realpath is
            opened with O_NOFOLLOW so a swapped parent cannot redirect the read
        expected: lstat recorded during collection; the file must still match

    Returns:
        Hexadecimal hash string

    Raises:
        OSError: If the file is unreadable, dataless, special, or swapped
    """
    try:
        if root is None:
            return fsread.hash_file(file_path, algorithm).digest
        resolved, target = _beneath_resolved_root(root, file_path)
        return fsread.hash_file_beneath(resolved, target, algorithm, expected).digest
    except (OSError, fsread.FsReadError) as e:
        raise OSError(f"Cannot read file {file_path}: {e}") from e
