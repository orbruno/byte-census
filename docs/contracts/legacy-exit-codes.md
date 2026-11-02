# Legacy dupfind Exit-Code Matrix

Author: Orlando Bruno
Contract version: 1.0.0
Satisfies: WI-CONTRACTS AC-08; implemented by WI-RENAME AC-03 and WI-LEGACY-ADAPTER AC-01, AC-03, AC-04

`dupfind` is a frozen v1 adapter. Its errors stay as Click text on stderr (not the byte-census JSON error object). Test names refer to `test_duplicate_finder_cli.py`, which WI-RENAME moves to `tests/legacy/` with the same test names.

## Matrix

| Exit | Meaning | Case | v1 (1.0.0) | v2 (2.0.0) | Test |
|---|---|---|---|---|---|
| 0 | Success | JSON to stdout with progress enabled | 0 | 0 | `test_json_stdout_remains_machine_readable_with_progress_enabled` |
| 0 | Success | CSV to stdout | 0 | 0 | `test_csv_stdout_does_not_wrap_long_paths` |
| 0 | Success | Table saved with `--output` to a new file | 0 | 0 | `test_table_output_can_be_saved` |
| 2 | Argument misuse | `--min-size -1` rejected by Click | 2 | 2 | `test_negative_minimum_size_is_rejected` |
| 1 | Operational failure | `--output` in a missing parent directory | 1 | 1 | `test_missing_output_parent_is_a_cli_error_without_traceback` |
| 3 | Existing output file | `--output` names an existing regular file | 0, file overwritten | 3, file unchanged | `test_existing_output_file_exits_3_without_overwriting` (new, WI-LEGACY-ADAPTER AC-04) |
| 3 | Existing output file | `--output` names a symlink (dangling or not) | 0, target overwritten | 3, link and target unchanged | `test_output_symlink_exits_3_without_following` (new, WI-LEGACY-ADAPTER AC-04) |

The exit 3 rows are the one intentional v2 change to dupfind exit codes. All other codes keep current Click behavior.

Exit 3 details:

- `--output` opens with `O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW`, so an existing file or symlink is never written. There is no `--force`.
- stderr names the path and suggests choosing a new path or removing the existing file first.
- Only `legacy/report_writer.py` may perform this write (WI-RENAME AC-04, WI-SAFETY AC-03).
- `test_table_output_can_be_saved` writes to a path that does not exist, so it keeps passing under exclusive creation.

## Engine under v2

Orchestrator decision 2026-11-02: dupfind keeps the v1 scanner in `byte_census.legacy` and does not use the new duplicates engine, because the owner decision is a frozen v1 adapter. Its results therefore keep v1 content semantics: empty files can group when `--min-size` is 0, hard-linked names are reported as duplicates, mount points under the root are crossed, and files are hashed as found. The new engine's corrections are available only through `byte-census duplicates scan`.

The only v2 behavior changes in dupfind are the exit 3 output collision above, the deprecation notice on stderr, and the help layout (`Usage:` and `Example:` block).

Unchanged: a root that is a symlink yields no files (`test_root_symlink_is_skipped`); symlinks inside the tree are skipped (`test_single_directory_detects_content_duplicates_and_skips_symlink`); compare mode reports only cross-directory matches (`test_compare_mode_reports_only_cross_directory_matches`); unreadable files produce warnings on stderr and exit 0.

---

Last Updated: 2026-11-02
Author: Orlando Bruno
