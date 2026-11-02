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

- `shell=False`, `cwd="/"`, a timeout on every call (column above), stdout and stderr captured, stdin closed (`DEVNULL`).
- Each child starts in its own session (`start_new_session=True`). On a timeout the runner sends `SIGKILL` to the whole process group, so helpers a tool spawned cannot outlive it.
- Captured output is capped: 16 MiB of stdout and 1 MiB of stderr. A stream over its cap kills the process group and raises a typed error (`OutputTooLargeError`), reported as `failed`.
- Decision: `df`, `diskutil`, and `tmutil` are pinned to `/bin/df`, `/usr/sbin/diskutil`, and `/usr/bin/tmutil` and are never looked up on `PATH`. docker, uv, npm, and brew live in user-managed locations, so they are located with `shutil.which` on the inherited `PATH`; a result that is not an absolute path is rejected (`UntrustedExecutableError`, reported as `failed`), because an empty or relative `PATH` entry resolves to the working directory, where a planted file could otherwise run. An accepted result is resolved with `realpath`. A missing executable is reported as `not_installed`.
- Decision: the child environment is minimal and explicit, never the inherited environment. It contains `PATH`, `HOME`, `USER`, and `TMPDIR` when set, `LC_ALL=C` (so `df` and `diskutil` output is parseable regardless of locale), the tool's location variables listed below when set, and the tool's write-suppressing settings below. Everything else, including credentials and `NODE_OPTIONS`, is dropped.

### Tool write behavior and mitigation

| Tool | Write behavior without mitigation | Mitigation | Location variables passed through |
|---|---|---|---|
| npm | Every invocation, including `npm config get cache`, writes a debug log under `~/.npm/_logs` and deletes old logs beyond `logs-max`; a `.npmrc` in the working directory can redirect `logs-dir`; the update notifier may write a check timestamp. | `npm_config_logs_max=0` (no log file is written), `npm_config_update_notifier=false`, and `cwd="/"`, so no project `.npmrc` is read. Environment settings take precedence over every `.npmrc`. | `npm_config_cache`, `NPM_CONFIG_CACHE` |
| brew | Some commands auto-update Homebrew, send analytics, and print environment hints. `brew --cache` only prints a path, but the variables make that hold even if Homebrew changes its defaults. | `HOMEBREW_NO_AUTO_UPDATE=1`, `HOMEBREW_NO_ANALYTICS=1`, `HOMEBREW_NO_ENV_HINTS=1` | `HOMEBREW_CACHE` |
| docker | The CLI reads `~/.docker/config.json` and contexts; the listed read commands do not modify them. CLI hints are printed to the terminal only. | `DOCKER_CLI_HINTS=false`; only the read-only subcommands in the table can run. | `DOCKER_HOST`, `DOCKER_CONTEXT`, `DOCKER_CONFIG` |
| uv | `uv cache dir` prints the cache path without creating it (checked 2026-11-02 with a nonexistent `UV_CACHE_DIR`). | None needed beyond the allowlist. | `UV_CACHE_DIR`, `XDG_CACHE_HOME` |
| df, diskutil, tmutil | Read-only system tools for the listed arguments. | Pinned absolute paths. | none |

Residual risk: a tool's global configuration (for example a user-level `~/.npmrc` or a Docker CLI plugin) is still read, and a future tool version could add a write that these settings do not cover. Tests never execute docker, npm, or brew; they verify the argv, environment, and launch options through an injected fake launcher.

- A nonzero exit or a timeout becomes an `unavailable_sources` entry (`failed` or `timed_out`), or exit 4 when the source is required (see [envelope.md](envelope.md#exit-codes)).
- Each call increments `cost.subprocess_calls`; captured stdout length is added to `cost.subprocess_stdout_bytes`.
- No suggestion string, user path, or option value is ever passed to the runner. The only variable operand in the table is the `df` mount point, chosen from two constants.
- Not permitted, among others: `du`, `find`, `stat`, `docker system prune`, `docker images --filter` or any filter not in row 3, any `docker` call with extra arguments, `brew cleanup`, `uv cache prune`, `npm cache verify`, and any shell.

## Replaced commands

storage-inventory.sh and the experiment preview used `du`, `find`, and `stat`. byte-census replaces them with its own read-only walker so it can enforce the volume boundary, global hard-link identity, and per-entry coverage reporting ([parity-matrix.md](parity-matrix.md)).

---

Last Updated: 2026-11-02
Author: Orlando Bruno
