"""Tests for reading tool cache locations from configuration (no process runs)."""

import os
from pathlib import Path

import pytest

from byte_census import toolpaths
from byte_census.toolpaths import ToolPath, npm_cache_location


def write_npmrc(home: Path, text: str) -> Path:
    path = home / ".npmrc"
    path.write_text(text)
    return path


def test_default_is_home_dot_npm(tmp_path: Path) -> None:
    result = npm_cache_location({"HOME": str(tmp_path)})

    assert result == ToolPath(str(tmp_path / ".npm"), "default", None)


@pytest.mark.parametrize(
    "name", ["npm_config_cache", "NPM_CONFIG_CACHE", "Npm_Config_Cache"]
)
def test_environment_variable_wins_case_insensitively(
    tmp_path: Path, name: str
) -> None:
    write_npmrc(tmp_path, "cache=/from/npmrc\n")

    result = npm_cache_location({"HOME": str(tmp_path), name: "/from/env"})

    assert result.path == "/from/env"
    assert result.source == f"env:{name}"


def test_lowercase_environment_variable_is_preferred_when_both_exist(
    tmp_path: Path,
) -> None:
    environ = {
        "HOME": str(tmp_path),
        "NPM_CONFIG_CACHE": "/upper",
        "npm_config_cache": "/lower",
    }

    assert npm_cache_location(environ).path == "/lower"


def test_empty_environment_value_is_ignored(tmp_path: Path) -> None:
    result = npm_cache_location({"HOME": str(tmp_path), "npm_config_cache": ""})

    assert result.source == "default"


def test_environment_value_expands_tilde_and_home(tmp_path: Path) -> None:
    home = str(tmp_path)

    assert npm_cache_location({"HOME": home, "npm_config_cache": "~/c"}).path == (
        f"{home}/c"
    )
    assert npm_cache_location({"HOME": home, "npm_config_cache": "${HOME}/d"}).path == (
        f"{home}/d"
    )


def test_npmrc_cache_line_is_used(tmp_path: Path) -> None:
    rc = write_npmrc(
        tmp_path,
        "# comment\n; also comment\n\nregistry=https://example.invalid/\n"
        "  cache = ~/npm-cache  \n",
    )

    result = npm_cache_location({"HOME": str(tmp_path)})

    assert result.path == str(tmp_path / "npm-cache")
    assert result.source == f"npmrc:{rc}"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("cache=${HOME}/x", "{home}/x"),
        ('cache="/quoted/path"', "/quoted/path"),
        ("cache='/single'", "/single"),
        ("cache=/a=b", "/a=b"),
        ("cache=/first\ncache=/last", "/last"),
    ],
)
def test_npmrc_values_are_parsed_minimally(
    tmp_path: Path, line: str, expected: str
) -> None:
    write_npmrc(tmp_path, line + "\n")

    result = npm_cache_location({"HOME": str(tmp_path)})

    assert result.path == expected.format(home=tmp_path)


@pytest.mark.parametrize(
    "text",
    ["#cache=/commented\n", "cachedir=/other\n", "cache\n", "cache=\n", ""],
)
def test_npmrc_without_a_cache_value_falls_back_to_default(
    tmp_path: Path, text: str
) -> None:
    write_npmrc(tmp_path, text)

    result = npm_cache_location({"HOME": str(tmp_path)})

    assert result.source == "default"
    assert result.path == str(tmp_path / ".npm")


def test_symlinked_npmrc_is_read_through_its_target(tmp_path: Path) -> None:
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    target = dotfiles / "npmrc"
    target.write_text("cache=/linked\n")
    (tmp_path / ".npmrc").symlink_to(target)

    assert npm_cache_location({"HOME": str(tmp_path)}).path == "/linked"


def test_fifo_npmrc_is_not_read_and_is_noted(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / ".npmrc")

    result = npm_cache_location({"HOME": str(tmp_path)})

    assert result.source == "default"
    assert result.note == "npmrc_unreadable: not_regular_file"


def test_oversized_npmrc_is_not_parsed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(toolpaths, "NPMRC_MAX_BYTES", 8)
    write_npmrc(tmp_path, "cache=/too/long/for/the/limit\n")

    result = npm_cache_location({"HOME": str(tmp_path)})

    assert result.source == "default"
    assert result.note == "npmrc_unreadable: too_large"


def test_missing_home_is_unresolved() -> None:
    assert npm_cache_location({}) == ToolPath(None, "unresolved", "HOME is not set")


def test_nothing_is_created(tmp_path: Path) -> None:
    before = sorted(os.listdir(tmp_path))

    npm_cache_location({"HOME": str(tmp_path)})
    npm_cache_location({"HOME": str(tmp_path), "npm_config_cache": str(tmp_path / "c")})

    assert sorted(os.listdir(tmp_path)) == before


def test_result_is_immutable(tmp_path: Path) -> None:
    result = npm_cache_location({"HOME": str(tmp_path)})

    with pytest.raises(AttributeError):
        result.path = "/"  # type: ignore[misc]
