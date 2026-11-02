"""Read-only hashing and failed-write cleanup for the legacy dupfind command."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from byte_census import fsread
from byte_census.legacy import report_writer, scan
from byte_census.legacy.dupfind import find
from byte_census.legacy.hashing import calculate_hash
from byte_census.legacy.scan import find_duplicates_single


def test_regular_file_hash_matches_sha256(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"hello")
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert calculate_hash(path) == expected


def test_fifo_is_a_read_error_without_hanging(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(OSError, match="Cannot read file"):
        calculate_hash(fifo)


def test_symlink_swap_is_a_read_error_and_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_bytes(b"secret")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    with pytest.raises(OSError, match="Cannot read file"):
        calculate_hash(link)


def test_dataless_file_is_not_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "evicted.txt"
    path.write_bytes(b"data")
    real_lstat = os.lstat

    class Dataless:
        def __init__(self, info: os.stat_result) -> None:
            self.st_mode = info.st_mode
            self.st_flags = fsread.SF_DATALESS

    monkeypatch.setattr(fsread, "lstat", lambda p: Dataless(real_lstat(p)))
    opened: list[object] = []
    monkeypatch.setattr(os, "open", lambda *a, **k: opened.append(a))
    with pytest.raises(OSError, match="dataless"):
        calculate_hash(path)
    assert opened == []


def test_unreadable_candidate_is_a_warning_and_exit_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.txt").write_bytes(b"same")
    target = tmp_path / "b.txt"
    target.write_bytes(b"same")
    real = scan._repeated_size_candidates

    def swap_for_fifo(size_groups: dict[int, list[Path]]) -> list[Path]:
        candidates = real(size_groups)
        target.unlink()
        os.mkfifo(target)
        return candidates

    monkeypatch.setattr(scan, "_repeated_size_candidates", swap_for_fifo)
    duplicates, errors, _ = find_duplicates_single(tmp_path, quiet=True)
    assert duplicates == {}
    assert len(errors) == 1 and "b.txt" in errors[0]
    monkeypatch.undo()
    target.unlink()
    target.write_bytes(b"same")
    result = CliRunner().invoke(find, [str(tmp_path), "--quiet"])
    assert result.exit_code == 0


def test_surrogate_path_is_written_faithfully(tmp_path: Path) -> None:
    output = tmp_path / "report.txt"
    text = "path: " + os.fsdecode(b"/tmp/bad\xff/name") + "\n"
    report_writer.write_report(output, text)
    assert output.read_bytes() == b"path: /tmp/bad\xff/name\n"


def test_failed_write_removes_only_the_created_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import click

    output = tmp_path / "report.txt"

    monkeypatch.setattr(report_writer, "_write_text", _raise_enospc)
    with pytest.raises(click.ClickException, match="Cannot write output file"):
        report_writer.write_report(output, "data")
    assert not output.exists()


def _raise_enospc(descriptor: int, text: str) -> None:
    os.write(descriptor, b"partial")
    raise OSError(28, "No space left on device")


def test_cleanup_skips_a_file_replaced_by_someone_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import click

    output = tmp_path / "report.txt"

    def swap_then_fail(descriptor: int, text: str) -> None:
        output.unlink()
        output.write_text("other", encoding="utf-8")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(report_writer, "_write_text", swap_then_fail)
    with pytest.raises(click.ClickException):
        report_writer.write_report(output, "data")
    assert output.read_text(encoding="utf-8") == "other"


def test_surrogate_path_cli_has_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = Path(os.fsdecode(b"/x/bad\xff"))
    scan = lambda *a, **k: ({"h": [bad, bad]}, [], 2)
    monkeypatch.setattr("byte_census.legacy.dupfind.find_duplicates_single", scan)
    monkeypatch.setattr(
        "byte_census.legacy.dupfind.calculate_statistics", lambda *a: None
    )
    monkeypatch.setattr(
        "byte_census.legacy.dupfind.format_json_output", lambda d, s: f"{bad}\n"
    )
    output = tmp_path / "out.json"
    result = CliRunner().invoke(
        find, [str(tmp_path), "--quiet", "--format", "json", "--output", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert b"bad\xff" in output.read_bytes()
