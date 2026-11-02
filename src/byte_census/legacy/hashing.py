"""File hashing for the legacy dupfind command."""

import hashlib
from pathlib import Path


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
    except (OSError, PermissionError) as e:
        raise OSError(f"Cannot read file {file_path}: {e}")
