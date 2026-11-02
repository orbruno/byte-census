"""Single-process fsread.walk against a process-per-first-level-child prototype.

Usage:
    uv run python docs/benchmarks/2026-11-02-parallel-walk/bench.py ROOT single
    uv run python docs/benchmarks/2026-11-02-parallel-walk/bench.py ROOT parallel WORKERS

Both modes count entries the way tree_size._Tally does (WalkEntry, SkippedMount
and lstat errors) and sum allocated bytes (st_blocks * 512) once per inode:
single-link inodes are summed directly, multi-link inodes are keyed by
(st_dev, st_ino) and merged globally. The parallel mode merges worker results
in path order, so the first path that claims a linked inode owns it. The root
itself is not counted. Read-only: fsread never writes.

Author: Orlando Bruno
"""

import json
import multiprocessing
import os
import resource
import stat
import sys
import time

from byte_census import fsread


def _tally(items, totals: dict, linked: dict) -> None:
    for item in items:
        if isinstance(item, fsread.WalkEntry):
            totals["entries"] += 1
            info = item.stat
            blocks = info.st_blocks * 512
            if info.st_nlink > 1:
                linked.setdefault((info.st_dev, info.st_ino), blocks)
            else:
                totals["allocated"] += blocks
        elif isinstance(item, fsread.SkippedMount):
            totals["entries"] += 1
        else:
            totals["errors"] += 1
            totals["entries"] += 1 if item.operation == "lstat" else 0


def _new_totals() -> dict:
    return {"entries": 0, "allocated": 0, "errors": 0}


def _finish(totals: dict, linked: dict) -> dict:
    return {**totals, "allocated": totals["allocated"] + sum(linked.values()),
            "linked_inodes": len(linked)}


def run_single(root: str) -> dict:
    totals, linked = _new_totals(), {}
    _tally(fsread.walk(root), totals, linked)
    return _finish(totals, linked)


def _worker(path: str) -> tuple[str, dict, list]:
    """Walk one first-level directory; return its totals and linked inodes."""
    totals, linked = _new_totals(), {}
    start = time.perf_counter()
    _tally(fsread.walk(path), totals, linked)
    totals["seconds"] = round(time.perf_counter() - start, 2)
    return path, totals, sorted(linked.items())


def _first_level(root: str) -> tuple[list, list[str]]:
    """Return root-level items (counted in the parent) and child dirs to farm out."""
    root_dev = fsread.lstat(root).st_dev
    items = fsread.list_directory(root, root_dev)
    subdirs = [
        item.path for item in items
        if isinstance(item, fsread.WalkEntry) and stat.S_ISDIR(item.stat.st_mode)
        and not item.is_dataless
    ]
    return items, subdirs


def _expand(root: str, depth: int) -> tuple[list, list[str]]:
    """List levels 1..depth-1 in the parent; directories at `depth` become tasks."""
    items, frontier = _first_level(root)
    for _ in range(depth - 1):
        next_frontier = []
        for path in frontier:
            level_items, subdirs = _first_level(path)
            items.extend(level_items)
            next_frontier.extend(subdirs)
        frontier = next_frontier
    return items, frontier


def run_parallel(root: str, workers: int, depth: int = 1) -> dict:
    totals, linked = _new_totals(), {}
    items, subdirs = _expand(root, depth)
    _tally(items, totals, linked)
    with multiprocessing.get_context("spawn").Pool(workers) as pool:
        results = list(pool.imap_unordered(_worker, subdirs, chunksize=1))
    slowest = sorted(results, key=lambda r: -r[1]["seconds"])[:5]
    for path, part, _ in slowest:
        print(f"worker {path}: {part['seconds']} s, {part['entries']} entries",
              file=sys.stderr)
    for _path, part, part_linked in sorted(results, key=lambda r: os.fsencode(r[0])):
        for key in ("entries", "allocated", "errors"):
            totals[key] += part[key]
        for inode, blocks in part_linked:
            linked.setdefault(tuple(inode), blocks)
    return _finish(totals, linked)


def main() -> None:
    root, mode = sys.argv[1], sys.argv[2]
    start = time.perf_counter()
    if mode == "single":
        result = run_single(root)
    else:
        depth = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        result = run_parallel(root, int(sys.argv[3]), depth)
    elapsed = time.perf_counter() - start
    label = mode if mode == "single" else f"parallel-{sys.argv[3]}-depth{depth}"
    mib = 1024 * 1024  # macOS ru_maxrss is in bytes
    rss = {
        "parent_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // mib,
        "max_child_rss_mib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss // mib,
    }
    print(json.dumps({"mode": label, "seconds": round(elapsed, 2), **result, **rss}))


if __name__ == "__main__":
    main()
