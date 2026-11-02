"""Regression tests for duplicate detection and CLI output contracts."""

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from byte_census.legacy.dupfind import find
from byte_census.legacy.hashing import calculate_hash
from byte_census.legacy.scan import (
    collect_files,
    find_duplicates_compare,
    find_duplicates_single,
)


class DuplicateFinderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_file(self, relative_path: str, content: bytes) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_single_directory_detects_content_duplicates_and_skips_symlink(
        self,
    ) -> None:
        first = self.write_file("single/first.txt", b"same content")
        second = self.write_file("single/nested/second.bin", b"same content")
        self.write_file("single/unique.txt", b"unique")
        (self.root / "single/link.txt").symlink_to(first)

        duplicates, errors, files_scanned = find_duplicates_single(
            self.root / "single", quiet=True
        )

        self.assertEqual(errors, [])
        self.assertEqual(files_scanned, 3)
        self.assertEqual(list(duplicates.values()), [[first, second]])

    def test_root_symlink_is_skipped(self) -> None:
        target = self.write_file("target.txt", b"content")
        link = self.root / "link.txt"
        link.symlink_to(target)

        self.assertEqual(collect_files(link), [])

    def test_single_directory_hashes_only_repeated_size_candidates(self) -> None:
        self.write_file("scan/duplicate-a.txt", b"duplicate")
        self.write_file("scan/duplicate-b.txt", b"duplicate")
        self.write_file("scan/unique.txt", b"a different size")

        with patch(
            "byte_census.legacy.scan.calculate_hash", wraps=calculate_hash
        ) as mocked_hash:
            find_duplicates_single(self.root / "scan", quiet=True)

        self.assertEqual(mocked_hash.call_count, 2)

    def test_compare_mode_reports_only_cross_directory_matches(self) -> None:
        first = self.write_file("left/shared-a.txt", b"shared")
        second = self.write_file("right/shared-b.txt", b"shared")
        self.write_file("left/only-left.txt", b"left only")
        self.write_file("right/only-right.txt", b"right only")

        duplicates, errors, files_scanned = find_duplicates_compare(
            self.root / "left", self.root / "right", quiet=True
        )

        self.assertEqual(errors, [])
        self.assertEqual(files_scanned, 4)
        self.assertEqual(list(duplicates.values()), [[first, second]])

    def test_json_stdout_remains_machine_readable_with_progress_enabled(self) -> None:
        self.write_file("json/first.txt", b"duplicate")
        self.write_file("json/second.txt", b"duplicate")

        result = self.runner.invoke(find, [str(self.root / "json"), "--format", "json"])

        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"]["files_scanned"], 2)
        self.assertEqual(report["summary"]["duplicate_groups"], 1)

    def test_csv_stdout_does_not_wrap_long_paths(self) -> None:
        long_directory = "long-" + ("x" * 120)
        self.write_file(f"{long_directory}/first.txt", b"duplicate")
        self.write_file(f"{long_directory}/second.txt", b"duplicate")

        result = self.runner.invoke(
            find,
            [str(self.root / long_directory), "--quiet", "--format", "csv"],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        rows = list(csv.reader(io.StringIO(result.stdout)))
        self.assertEqual(rows[0], ["hash", "file_count", "size_bytes", "file_path"])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(Path(row[3]).is_file() for row in rows[1:]))

    def test_table_output_can_be_saved(self) -> None:
        self.write_file("table/first.txt", b"duplicate")
        self.write_file("table/second.txt", b"duplicate")
        output_path = self.root / "table-report.txt"

        result = self.runner.invoke(
            find,
            [str(self.root / "table"), "--quiet", "--output", str(output_path)],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        report = output_path.read_text(encoding="utf-8")
        self.assertIn("Found 1 duplicate groups", report)
        self.assertIn(str(self.root / "table/first.txt"), report)

    def test_missing_output_parent_is_a_cli_error_without_traceback(self) -> None:
        self.write_file("output/first.txt", b"duplicate")
        self.write_file("output/second.txt", b"duplicate")

        result = self.runner.invoke(
            find,
            [
                str(self.root / "output"),
                "--quiet",
                "--format",
                "json",
                "--output",
                str(self.root / "missing/report.json"),
            ],
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Cannot write output file", result.stderr)
        self.assertNotIn("Traceback", result.output)

    def test_negative_minimum_size_is_rejected(self) -> None:
        self.write_file("minimum/file.txt", b"content")

        result = self.runner.invoke(
            find, [str(self.root / "minimum"), "--min-size", "-1"]
        )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("not in the range", result.stderr)

    def test_usage_error_hint_names_long_help_option(self) -> None:
        self.write_file("usage/file.txt", b"content")

        result = self.runner.invoke(
            find, ["-X", str(self.root / "usage")], prog_name="dupfind"
        )

        self.assertEqual(result.exit_code, 2)
        self.assertIn("Try 'dupfind --help' for help.", result.stderr)


if __name__ == "__main__":
    unittest.main()
