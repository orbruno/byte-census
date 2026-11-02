# Parallel walk benchmark, 2026-11-02

Author: Orlando Bruno

Work Item: WI-PARALLEL-WALK, Phase 1 (measurement only, no production change).
Machine: Apple Silicon, 10 cores, 32 GiB, APFS. Code: base d2d1472, `fsread.walk` by descriptor.

## Method

`bench.py` counts entries the way `tree_size._Tally` does (WalkEntry, SkippedMount, lstat errors) and sums `st_blocks * 512` once per inode. Multi-link inodes are keyed by `(st_dev, st_ino)` and merged globally in the parent in byte order of the task path, so the first path claims a linked inode. Modes:

- `single`: one `fsread.walk(root)`.
- `parallel N D`: the parent lists levels 1 to D-1 with `fsread.list_directory`; every directory at depth D is one task, walked by `fsread.walk` in a spawn pool of N processes. D=1 is the process-per-first-level-child prototype the Work Item names.

Times are the in-process `perf_counter` wall time. Peak RSS comes from `/usr/bin/time -l` (the `uv` process) and from `getrusage` inside the script (parent and largest reaped worker). No `purge`, no sudo.

## Results: ~/Documents (live tree, about 2.29 million entries)

| Mode | Runs (s) | Median (s) | Speedup |
|---|---|---:|---:|
| single (round A) | 75.37, 82.04, 80.46 | 80.46 | 1.00 |
| parallel 4, depth 1 | 77.89, 80.33, 74.97 | 77.89 | 1.03 |
| parallel 8, depth 1 | 77.26, 75.28, 69.31 | 75.28 | 1.07 |
| single (round B) | 77.65, 75.60, 78.91 | 77.65 | 1.00 |
| parallel 8, depth 3 | 30.79, 27.57, 30.34 | 30.34 | 2.56 |

Depth 1 does not help: one first-level folder holds 2,061,221 of 2,291,278 entries, and its single worker takes 68 s . Depth 3 balances the work; the slowest tasks are subtree A (712,534 entries, 27 to 30 s) and subtree B (630,309 entries, 25 to 27 s), which now set the floor.

CPU: single uses 10 s user and 34 to 37 s sys in 75 to 82 s wall, so about 35 s are spent off CPU. `kern.maxvnodes` is 263,168, about one ninth of the tree, so no pass over ~/Documents is warm at the vnode level: each pass evicts the metadata of the previous one. Parallel depth 3 uses 13 to 14 s user and 50 to 54 s sys, and overlaps that metadata latency.

## Agreement

- Static trees agree exactly in every mode. a static ~/Documents subfolder: 191,555 entries, 41,444,585,472 allocated bytes, 3,955 linked inodes, 0 errors, in all 12 runs. `/Applications`: 1,129,742 entries, 148,344,573,952 bytes, 208,004 linked inodes, 1 error, in all 4 runs.
- ~/Documents is written by other sessions (agent worktrees live inside it). Counts grow monotonically over the session (2,286,669 to 2,291,353) and adjacent runs differ by 0 to 37 entries in that same direction. Example: depth 3 round 2 and the preceding single both report 2,291,309 entries; allocated differs by 8,192 bytes. No mode disagreement beyond that drift was observed.

## Memory (peak RSS)

- single: 53 to 60 MiB.
- parallel depth 1: parent 96 to 101 MiB; largest worker 104 to 111 MiB (the one first-level folder worker).
- parallel depth 3: parent 96 to 98 MiB; largest worker 45 to 48 MiB. With 8 workers the total footprint can reach about 480 MiB.
- The walk itself stays near 60 MiB, so the 460 MB peak of `byte-census artifacts scan ~/Documents` comes from elsewhere in that pipeline.

## Cold-ish pass

The benchmark had not yet touched `/Applications`, and both earlier ~/Documents passes had already flushed the vnode cache. The first run was parallel 8 depth 2: 11.91 s. It was followed by single 37.28 s, parallel 13.96 s and single 34.29 s, so a cold parallel run is about 2.5 to 3 times faster than single. A cold static-subfolder single run after that took 6.46 s, against 1.0 to 1.2 s warm. The disk buffer cache could not be dropped without privileges, so this is cold for the vnode cache only. On a tiny tree (Downloads, 2,327 entries) the spawn cost dominates: parallel takes 0.12 to 0.44 s, single 0.02 s.

## Profile of the single-process walk

cProfile, warm a static ~/Documents subfolder (1.0 s unprofiled, 2.1 s profiled):

| Cost | tottime (s) | Note |
|---|---:|---|
| `posix.stat` (fstatat) | 0.50 | kernel, one per entry |
| `posixpath.join` (383,110 calls) | 0.50 cumulative | two joins per entry |
| `_step` | 0.20 | per-entry dispatch |
| `_sorted_entries` | 0.74 cumulative | builds an `_Entry` with a joined path for every name, then `_list_names` keeps only `.name` |
| `sorted` with `os.fsencode` key | 0.29 cumulative | |
| `posix.scandir`, `posix.open` | 0.05, 0.07 | |

Recommendation (advisory, no change made): list names directly (for example `os.listdir(fd)` sorted by `os.fsencode`) instead of building `_Entry` objects and joined paths that `_list_names` throws away, and join each path only once in `_step`. That removes about half of the per-entry Python work, roughly 0.3 to 0.4 s of the 2.1 s profiled. On the full tree, Python user time is only 10 s of 80 s, so this optimization saves at most a few seconds there; the dominant cost is metadata I/O, which parallelism overlaps and the optimization does not.

## Reading

- The process-per-first-level-child prototype misses the 1.5 times bar on ~/Documents (1.03 to 1.07 times), because one child holds 90 percent of the entries.
- A balanced split clears it: parallel 8 depth 3 is 2.56 times faster warm and about 2.5 to 3 times faster cold-ish, with exact agreement on static trees.
- For Phase 2, split adaptively (expand any task above an entry or time budget into its children, or use a shared work queue) instead of a fixed depth, keep jobs at 1 below a size threshold, and merge linked inodes in path order as done here.

## Files

- `bench.py`: the benchmark (single and parallel N D modes).
- `run_warm.sh`: warm runner for round A.
- `raw-warm.txt`: round A (single, parallel 4 and 8 at depth 1).
- `raw-worker-split.txt`: per-worker times at depth 1.
- `raw-warm-depth3.txt`: round B (parallel 8 depth 3 against single).
- `raw-static-subtree.txt`: static subtree agreement and timing.
- `raw-cold-ish.txt`: first-touch passes on /Applications and Downloads.
- `raw-profile.txt`: cProfile output.

Commands: `uv run python bench.py ROOT single`, `uv run python bench.py ROOT parallel N D`, `sh run_warm.sh ROOT`.

Raw per-run outputs stayed local because they list private folder names; the tables above summarize them.
