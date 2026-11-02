# Changelog

All notable changes to this project are recorded here.

## Unreleased

### Changed

- `dupfind --output FILE` now creates the file exclusively. An existing file or
  a symlink (dangling or not) at the path exits 3, writes nothing, and names the
  path on stderr; there is no `--force`. A missing parent directory still exits 1.
- `dupfind` prints a deprecation notice on stderr (also with `--quiet`); stdout is
  unchanged. The adapter will be removed in 3.0.0.

### Added

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
