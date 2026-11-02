# External Command Allowlist

Author: Orlando Bruno
Contract version: 1.0.0
Satisfies: WI-CONTRACTS AC-06; enforced by WI-SAFETY AC-01 and AC-02

The runner is the only module that creates processes. It accepts an argv only if it matches one row of this table exactly: same tokens, same order, same count, with each variable operand passing its validator. Any other flag, filter, suffix, or extra trailing argument is rejected before a process starts. Nothing else is permitted.

## Table

`{{json .}}` below is the literal Go template text passed as one argv token. It renders each row as one JSON object per line.

| # | argv (one cell per token, space-separated) | Variable operand and validator | Used by | Timeout |
|---|---|---|---|---|
| 1 | `docker system df --format {{json .}}` | none | docker scan, disk map (informational) | 120 s |
| 2 | `docker images --format {{json .}}` | none | docker scan | 120 s |
| 3 | `docker images -f dangling=true -q` | none | docker scan | 120 s |
| 4 | `docker ps -a -f status=exited --format {{json .}}` | none | docker scan | 120 s |
| 5 | `uv cache dir` | none | caches scan, disk map | 60 s |
| 6 | `npm config get cache` | none | caches scan, disk map | 60 s |
| 7 | `brew --cache` | none | caches scan, disk map | 60 s |
| 8 | `df -k PATH` | `PATH` is exactly `/` or exactly `/System/Volumes/Data` | disk map | 60 s |
| 9 | `diskutil info /` | none | disk map | 60 s |
| 10 | `tmutil listlocalsnapshots /` | none | disk map | 60 s |

Exact argv lists, as the runner compares them:

```text
["docker", "system", "df", "--format", "{{json .}}"]
["docker", "images", "--format", "{{json .}}"]
["docker", "images", "-f", "dangling=true", "-q"]
["docker", "ps", "-a", "-f", "status=exited", "--format", "{{json .}}"]
["uv", "cache", "dir"]
["npm", "config", "get", "cache"]
["brew", "--cache"]
["df", "-k", "/"]
["df", "-k", "/System/Volumes/Data"]
["diskutil", "info", "/"]
["tmutil", "listlocalsnapshots", "/"]
```

## Runner rules

- `shell=False`, a timeout on every call (column above), stdout and stderr captured, stdin closed (`DEVNULL`).
- Decision: the executable for argv[0] is located with `shutil.which` on the inherited `PATH`, because docker, uv, npm, and brew live in user-managed locations. `df`, `diskutil`, and `tmutil` are resolved the same way; a missing executable is reported as `not_installed`.
- Decision: the child environment is the inherited environment with `LC_ALL=C` added, so `df` and `diskutil` output is parseable regardless of the user's locale.
- A nonzero exit or a timeout becomes an `unavailable_sources` entry (`failed` or `timed_out`), or exit 4 when the source is required (see [envelope.md](envelope.md#exit-codes)).
- Each call increments `cost.subprocess_calls`; captured stdout length is added to `cost.subprocess_stdout_bytes`.
- No suggestion string, user path, or option value is ever passed to the runner. The only variable operand in the table is the `df` mount point, chosen from two constants.
- Not permitted, among others: `du`, `find`, `stat`, `docker system prune`, `docker images --filter` or any filter not in row 3, any `docker` call with extra arguments, `brew cleanup`, `uv cache prune`, `npm cache verify`, and any shell.

## Replaced commands

storage-inventory.sh and the experiment preview used `du`, `find`, and `stat`. byte-census replaces them with its own read-only walker so it can enforce the volume boundary, global hard-link identity, and per-entry coverage reporting ([parity-matrix.md](parity-matrix.md)).

---

Last Updated: 2026-11-02
Author: Orlando Bruno
