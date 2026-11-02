"""Tests for scan-root validation (WI-SAFETY AC-06).

WI-CORE maps `PathValidationError` to exit code 3.
"""

import os
from pathlib import Path

import pytest

from byte_census.paths import PathValidationError, validate_root


def test_valid_directory_is_returned_resolved(tmp_path: Path) -> None:
    assert validate_root(str(tmp_path)) == Path(os.path.realpath(tmp_path))


def test_accepts_path_objects(tmp_path: Path) -> None:
    assert validate_root(tmp_path) == Path(os.path.realpath(tmp_path))


def test_symlinked_root_resolves_once(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)

    assert validate_root(link) == Path(os.path.realpath(target))


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("a\x00b", "null_byte"),
        ("dir\nname", "control_character"),
        ("dir\x1b[31m", "control_character"),
        ("tab\there", "control_character"),
        ("del\x7f", "control_character"),
        ("c1\x85", "control_character"),
        ("", "empty"),
    ],
)
def test_rejects_unsafe_characters(value: str, reason: str) -> None:
    with pytest.raises(PathValidationError) as caught:
        validate_root(value)

    assert caught.value.reason == reason


def test_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(PathValidationError) as caught:
        validate_root(tmp_path / "missing")

    assert caught.value.reason == "not_found"


def test_rejects_regular_file(tmp_path: Path) -> None:
    file_path = tmp_path / "f.txt"
    file_path.write_text("x")

    with pytest.raises(PathValidationError) as caught:
        validate_root(file_path)

    assert caught.value.reason == "not_a_directory"


def test_rejects_fifo(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)

    with pytest.raises(PathValidationError) as caught:
        validate_root(fifo)

    assert caught.value.reason == "not_a_directory"


def test_rejects_inaccessible_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def denied(path: str) -> os.stat_result:
        raise PermissionError(13, "Permission denied", path)

    monkeypatch.setattr("byte_census.paths.os.stat", denied)

    with pytest.raises(PathValidationError) as caught:
        validate_root(tmp_path)

    assert caught.value.reason == "inaccessible"


def test_error_carries_path_and_message(tmp_path: Path) -> None:
    with pytest.raises(PathValidationError) as caught:
        validate_root(tmp_path / "nope")

    assert caught.value.path == str(tmp_path / "nope")
    assert "nope" in str(caught.value)
    assert isinstance(caught.value, ValueError)


def test_rejects_non_path_type() -> None:
    with pytest.raises(PathValidationError) as caught:
        validate_root(b"/tmp")  # type: ignore[arg-type]

    assert caught.value.reason == "invalid_type"
