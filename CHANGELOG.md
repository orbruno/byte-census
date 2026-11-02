# Changelog

All notable changes to this project are recorded here.

## Unreleased

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
