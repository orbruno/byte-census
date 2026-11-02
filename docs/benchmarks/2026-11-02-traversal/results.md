# Traversal benchmark, 2026-11-02

Author: Orlando Bruno

Tree: one development workspace folder. Apple Silicon, 8 performance and 2 efficiency cores.

## Equal-work run (authoritative)

`walk_mp.py` scans the root's own entries in the parent process, then each child directory in a worker, so it visits the same entries as `walk.py single`. All three methods agree exactly: 8,286,834,688 allocated bytes and 351,947 entries.

| Method | Pass 1 (cache partly cold) | Pass 2 (warm) |
|---|---:|---:|
| Python, 1 process (`walk.py single`) | 13.3 s | 5.1 s |
| Python, 4 processes (`walk_mp.py 4`) | 3.9 s | 3.6 s |
| Python, 10 processes (`walk_mp.py 10`) | 3.7 s | 3.1 s |

## Earlier exploratory run (indicative only)

Same tree, about 351,711 entries a few minutes earlier, warm cache. `walk.py threads` and the first version of `walk_mp.py` scanned only child-directory descendants, so their work was not identical to the single-process walk; the Rust and du runs scanned the whole tree.

| Method | Time |
|---|---:|
| `du -sk` | 10.3 s |
| Rust, 1 thread (`walk.rs`) | 11.9 s |
| Python, 1 process | 6.2 s |
| Python, 10 threads (child scope) | 6.3 s |
| Rust, 4 threads | 5.5 s |
| `du` in 10 parallel processes | 3.4 s |
| Rust, 10 threads | 3.4 s |

## Reading

The limit is filesystem metadata throughput, not language. Python threads do not help; Python processes reach the time of Rust threads (3.1 to 3.7 s against 3.4 s), a 1.6 times warm speedup over one process. Cold-cache behavior varies widely and a larger tree was not measured; WI-PARALLEL-WALK owns that measurement.

Commands: `uv run --no-project python -I walk.py ROOT single|threads`, `uv run --no-project python -I walk_mp.py ROOT WORKERS`, `rustc -O walk.rs -o walkrs && ./walkrs ROOT THREADS`.
