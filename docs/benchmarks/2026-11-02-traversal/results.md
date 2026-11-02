# Traversal benchmark, 2026-11-02

Author: Orlando Bruno

Tree: one development workspace folder, 351,711 to 351,858 entries (the tree changed slightly between runs), 8.29 GB allocated. Warm cache. Apple Silicon, 8 performance and 2 efficiency cores. All methods agree on the total.

| Method | Time |
|---|---:|
| `du -sk` | 10.3 s |
| Rust, 1 thread (`walk.rs`) | 11.9 s |
| Python `os.scandir`, 1 process (`walk.py single`) | 5.8 to 6.2 s |
| Python, 10 threads (`walk.py threads`) | 6.3 s |
| Rust, 4 threads | 5.5 s |
| Python, 4 processes (`walk_mp.py 4`) | 5.7 s |
| `du` in 10 parallel processes | 3.4 s |
| Rust, 10 threads | 3.4 s |
| Python, 10 processes, global hard-link merge (`walk_mp.py 10`) | 3.4 s |

Reading: the limit is filesystem metadata throughput, not language. Threads do not help Python; processes reach the same time as Rust threads. Cold-cache runs and a larger tree were not measured.

Commands: `uv run --no-project python -I walk.py ROOT single|threads`, `uv run --no-project python -I walk_mp.py ROOT WORKERS`, `rustc -O walk.rs -o walkrs && ./walkrs ROOT THREADS`.
