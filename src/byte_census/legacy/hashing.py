"""File hashing for the legacy dupfind command."""

from pathlib import Path

from byte_census import fsread


def calculate_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """
    Calculate cryptographic hash of a file using chunked reading.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use (default: sha256)

    Returns:
        Hexadecimal hash string

    Raises:
        OSError: If the file is unreadable, dataless, special, or swapped
    """
    try:
        return fsread.hash_file(file_path, algorithm).digest
    except (OSError, fsread.FsReadError) as e:
        raise OSError(f"Cannot read file {file_path}: {e}") from e
