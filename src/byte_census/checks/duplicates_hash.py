"""Hashing stages of `duplicates scan` (WI-DUPLICATES AC-01, AC-02, AC-05).

Every content read goes through `fsread.open_regular_file`, which accepts
regular files only, refuses dataless files, and checks the descriptor's
identity. Each read also compares the descriptor's `fstat` before and after
reading with the size and mtime seen at collection; any difference, a short
read, or a vanished file excludes the file and lists it in
`incomplete_coverage`. Bytes returned by `os.read` are counted even when the
file is then excluded, so `content_bytes_read` is exact.
"""

import errno
import hashlib
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from byte_census import fsread
from byte_census.checks.duplicates_collect import Inode
from byte_census.model import CoverageEntry

PARTIAL_BYTES = 64 * 1024
CHUNK = fsread.CHUNK_SIZE
CHANGED = "changed_during_scan"


@dataclass(frozen=True)
class Digest:
    """A digest of one inode, or the coverage entry that excluded it."""

    inode: Inode
    sha256: str | None
    bytes_read: int
    coverage: CoverageEntry | None = None


@dataclass(frozen=True)
class StageResult:
    """Digests of the inodes that stayed valid, and the ones excluded."""

    digests: tuple[tuple[Inode, str], ...]
    coverage: tuple[CoverageEntry, ...]
    bytes_read: int


def _chunks(fd: int, limit: int) -> Iterator[bytes]:
    """Yield reads from fd until `limit` bytes or end of file."""
    remaining = limit
    while remaining > 0:
        chunk = os.read(fd, min(CHUNK, remaining))
        if not chunk:
            return
        remaining -= len(chunk)
        yield chunk


def _unchanged(info: Any, inode: Inode) -> bool:
    identity = (info.st_dev, info.st_ino) == inode.key
    return identity and (info.st_size, info.st_mtime_ns) == (
        inode.size,
        inode.mtime_ns,
    )


def _excluded(inode: Inode, read: int, reason: str, code: Any, op: str) -> Digest:
    name = errno.errorcode.get(code) if isinstance(code, int) else None
    return Digest(inode, None, read, CoverageEntry(inode.primary, reason, name, op))


def _refused(inode: Inode, error: fsread.FsReadError) -> Digest:
    reason = "dataless" if isinstance(error, fsread.DatalessFileError) else CHANGED
    operation = "open" if reason == "dataless" else "hash"
    return _excluded(inode, 0, reason, None, operation)


def digest_inode(inode: Inode, limit: int | None) -> Digest:
    """SHA-256 of the first `limit` bytes (all bytes when None)."""
    expected = inode.size if limit is None else min(inode.size, limit)
    digest = hashlib.sha256()
    total = 0
    try:
        with fsread.open_regular_file(inode.primary) as fd:
            if not _unchanged(os.fstat(fd), inode):
                return _excluded(inode, 0, CHANGED, None, "hash")
            try:
                for chunk in _chunks(fd, expected):
                    digest.update(chunk)
                    total += len(chunk)
            except OSError as error:
                reason = fsread.coverage_reason(error.errno)
                return _excluded(inode, total, reason, error.errno, "read")
            if total != expected or not _unchanged(os.fstat(fd), inode):
                return _excluded(inode, total, CHANGED, None, "hash")
    except fsread.FsReadError as error:
        return _refused(inode, error)
    except OSError as error:
        reason = fsread.coverage_reason(error.errno)
        return _excluded(inode, total, reason, error.errno, "open")
    return Digest(inode, digest.hexdigest(), total)


def hash_stage(inodes: Iterable[Inode], limit: int | None) -> StageResult:
    """Hash each inode once; excluded inodes go to coverage."""
    results = tuple(digest_inode(inode, limit) for inode in inodes)
    return StageResult(
        digests=tuple((r.inode, r.sha256) for r in results if r.sha256 is not None),
        coverage=tuple(r.coverage for r in results if r.coverage is not None),
        bytes_read=sum(r.bytes_read for r in results),
    )
