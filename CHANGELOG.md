# Changelog

All notable changes to this project are recorded here.

## Unreleased

### Fixed

- `dupfind` hashes through the safe reader: dataless (evicted) files are not
  downloaded, FIFOs and other special files do not hang the scan, and a file
  swapped for a symlink is not followed. Each becomes a per-file warning on
  stderr and the run still exits 0. Output for regular files is unchanged.
- `dupfind --output` writes undecodable path bytes faithfully, and a failed write
  removes the file it created (only if it is still the same inode) and exits 1
  with "Cannot write output file" instead of a traceback.

### Changed

- `dupfind --output FILE` now creates the file exclusively. An existing file or
  a symlink (dangling or not) at the path exits 3, writes nothing, and names the
  path on stderr; there is no `--force`. A missing parent directory still exits 1.
- `dupfind` prints a deprecation notice on stderr (also with `--quiet`); stdout is
  unchanged. The adapter will be removed in 3.0.0.
- The `byte-census` group reports usage errors as JSON on stderr instead of
  Click's plain-text usage message; the exit code stays 2.
- A missing option value and an interruption (Ctrl-C) now name the subcommand
  in the error's `help`, and stderr holds exactly one JSON object. Every runner
  failure other than a rejected argv (including an untrusted executable path
  and oversized output) exits 4.
- `meta.cost.elapsed_s` is defined as the time from the start of the command
  callback until the envelope is complete, just before serialization.
- Snapshots keep field order and the cost counters; only `elapsed_s`,
  `captured_at`, integer `st_dev`, and finding IDs are masked, and every
  finding ID is checked against the ID rule before masking.

### Added

- Cleanup suggestion catalog (`byte_census.suggestions`): nine immutable entries
  (docker, uv, brew, npm, artifact, duplicate) with risk, reversibility, and
  reason, pure builders for check-wide and per-finding suggestions, and the
  low-to-high risk ordering. Suggestions are text only, always require owner
  authorization, and never reach the runner.
- Snapshot test helper (`tests/support/snapshots.py`) that normalizes
  `captured_at`, `cost`, `scope.st_dev`, and fixture roots; snapshots update
  only with `BYTE_CENSUS_UPDATE_SNAPSHOTS=1`.
- Coverage gate: `uv run pytest` fails below 80 percent line coverage.
- GitHub Actions workflow running ruff and the full suite on `macos-latest`.
- `byte_census.runner`, the only process gateway. It runs an argv only when
  it exactly matches a row of `docs/contracts/argv-allowlist.md`, with
  `shell=False`, a per-row timeout, stdin closed, and `LC_ALL=C`; it raises
  typed errors for rejected argv, missing executables, and timeouts.
- `byte_census.fsread`, read-only filesystem primitives: content reads
  `lstat`, require a regular file, open with
  `O_RDONLY | O_NOFOLLOW | O_NONBLOCK`, and re-check identity with `fstat`.
  FIFOs, devices, sockets, symlinks, and dataless (`SF_DATALESS`) files are
  never read. The walker never follows symlinks and never crosses an
  `st_dev` change.
- `byte_census.paths.validate_root`, which rejects empty paths, null bytes,
  control characters, missing paths, and non-directories.
- AST read-only guard test: process access only in the runner, write
  operations only in `legacy/report_writer.py`, and `ctypes`, `pty`,
  `tempfile`, `multiprocessing`, `os.fork`, `os.posix_spawn`, and dynamic
  `getattr(os, ...)` forbidden everywhere.
- Test that hashing and walking a fixture tree leave contents and
  modification times unchanged; reading may update access times.
- Observation core (WI-CORE): `byte_census.model` with frozen dataclasses for
  the `{data, meta}` envelope, findings (including classification fields),
  suggestions, coverage entries, cost, and the error object, serialized in
  contract field order, plus the contract ordering helpers and the finding ID
  rule.
- `byte_census.cost`: one wall-clock `elapsed_s` per command and mergeable
  counters for content bytes read, entries visited, and subprocess calls and
  stdout bytes; unmeasurable values are null with a note, never zero.
- `byte_census.errors`: typed errors mapped to exit codes 1 (internal),
  2 (usage), 3 (validation), and 4 (source unavailable). Every byte-census
  error, including Click usage errors, is one JSON object on stderr with an
  empty stdout and no traceback.
- `--format json|table` scaffold for checks (`byte_census.command`). JSON is
  the default; the table view uses no ANSI codes when stdout is not a TTY or
  `NO_COLOR` is set.
- Hidden internal command `byte-census _selftest`, not shown in `--help` and
  not part of the public contract, which exercises the scaffold end to end.
- Snapshot helper normalizes `meta.scope.roots[].st_dev` and path-derived IDs
  in `id`, `finding_id`, `finding_ids`, and `suggestion_ids`.

### Security

- The runner pins `df`, `diskutil`, and `tmutil` to absolute system paths,
  rejects relative `PATH` lookups for docker, uv, and brew, runs every
  child with `cwd="/"` in its own session, kills the whole process group on
  timeout, and caps captured output.
- Children get a minimal explicit environment; Homebrew auto-update,
  analytics, and hints are switched off.
- npm is no longer run at all, because every npm invocation writes or deletes
  debug logs. `byte_census.toolpaths.npm_cache_location` reads the npm cache
  location from `npm_config_cache`, `~/.npmrc`, or the `~/.npm` default.
- The walker no longer lists dataless directories (recorded as `dataless`)
  and is iterative. `validate_root` resolves the path before checking it.
- The AST guard now allowlists importable modules and every attribute of
  each module, rejects chains that pass through one module to reach another,
  rejects argument unpacking in file openers, and catches aliasing, dynamic
  attribute access, re-exports, and write methods in any position.

## 2.0.0

### Changed

- The project is now `byte-census` 2.0.0. The package moved from
  `duplicate_finder_cli` to a src layout at `src/byte_census/`.
- The v1 duplicate finder code now lives in `byte_census.legacy`, split into
  small modules. `report_writer.py` is the only module that writes files.
- The `dupfind` help text now uses an `Example:` block (previously `Examples:`)
  and accepts `-h` as well as `--help`. All other `dupfind` behavior is unchanged.

### Added

- `byte-census` entry point, an empty command group. `byte-census --version`
  prints `byte-census 2.0.0`; bare invocation shows help and exits 0.
- Dev dependency group with pytest, pytest-cov, and ruff.
