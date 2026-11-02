"""Staged grouping for `duplicates scan` (WI-DUPLICATES AC-01, AC-02).

Size first, then a SHA-256 of the first 64 KiB, then a full SHA-256 only for
partial matches larger than 64 KiB. A file of 64 KiB or less is read whole in
the partial stage, so its partial digest is its content digest and it is
never read twice. With `--compare`, a group survives a stage only when its
inodes were seen under both roots, so single-side groups are never hashed.
"""

from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from byte_census.checks import duplicates_hash
from byte_census.checks.duplicates_collect import LEFT, RIGHT, Inode
from byte_census.model import CoverageEntry

BOTH_SIDES = frozenset({LEFT, RIGHT})
Item = TypeVar("Item")


@dataclass(frozen=True)
class Group:
    """Inodes with identical content, ordered by primary path."""

    content_sha256: str
    partial_sha256: str
    members: tuple[Inode, ...]


@dataclass(frozen=True)
class Outcome:
    """Groups plus the stage counts, exclusions, and bytes read."""

    groups: tuple[Group, ...]
    size_candidates: int
    partial_hash_candidates: int
    coverage: tuple[CoverageEntry, ...]
    bytes_read: int


def _bucket(
    items: Iterable[Item],
    key: Callable[[Item], Hashable],
    inode_of: Callable[[Item], Inode],
    compare: bool,
) -> tuple[tuple[Item, ...], ...]:
    """Groups of two or more items with equal keys, in first-seen order."""
    buckets: dict[Hashable, list[Item]] = {}
    for item in items:
        buckets.setdefault(key(item), []).append(item)

    def keep(bucket: Sequence[Item]) -> bool:
        sides = frozenset().union(*(inode_of(item).sides for item in bucket))
        return len(bucket) > 1 and (not compare or sides == BOTH_SIDES)

    return tuple(tuple(bucket) for bucket in buckets.values() if keep(bucket))


def _flat(buckets: Iterable[Iterable[Item]]) -> tuple[Item, ...]:
    return tuple(item for bucket in buckets for item in bucket)


Hashed = tuple[Inode, str]


def _first(item: Hashed) -> Inode:
    return item[0]


def _content_digests(
    partial: Sequence[Hashed], full: Sequence[Hashed]
) -> tuple[tuple[Inode, str, str], ...]:
    """(inode, partial, content) for every inode that has a content digest."""
    by_key = {inode.key: digest for inode, digest in full}
    triples = []
    for inode, digest in partial:
        if inode.size <= duplicates_hash.PARTIAL_BYTES:
            triples.append((inode, digest, digest))
        elif inode.key in by_key:
            triples.append((inode, digest, by_key[inode.key]))
    return tuple(triples)


def _to_group(bucket: Sequence[tuple[Inode, str, str]]) -> Group:
    members = tuple(sorted((item[0] for item in bucket), key=lambda i: i.primary))
    return Group(bucket[0][2], bucket[0][1], members)


def find_groups(inodes: Sequence[Inode], compare: bool) -> Outcome:
    """Run the three stages over the collected inodes."""
    by_size = _bucket(inodes, lambda i: i.size, lambda i: i, compare)
    partial = duplicates_hash.hash_stage(_flat(by_size), duplicates_hash.PARTIAL_BYTES)
    by_partial = _bucket(partial.digests, lambda h: (h[0].size, h[1]), _first, compare)
    matched = _flat(by_partial)
    large = (i for i, _ in matched if i.size > duplicates_hash.PARTIAL_BYTES)
    full = duplicates_hash.hash_stage(large, None)
    triples = _content_digests(matched, full.digests)
    by_content = _bucket(triples, lambda t: (t[0].size, t[2]), _first, compare)
    groups = tuple(_to_group(bucket) for bucket in by_content)
    return Outcome(
        groups=groups,
        size_candidates=len(_flat(by_size)),
        partial_hash_candidates=len(matched),
        coverage=partial.coverage + full.coverage,
        bytes_read=partial.bytes_read + full.bytes_read,
    )
