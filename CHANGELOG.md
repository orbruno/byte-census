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
