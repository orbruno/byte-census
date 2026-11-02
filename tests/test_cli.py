"""Tests for the byte-census group and the dupfind help text."""

import pytest
from click.testing import CliRunner

from byte_census.cli import main as byte_census_main
from byte_census.legacy.dupfind import find as dupfind_command

COMMANDS = {"byte-census": byte_census_main, "dupfind": dupfind_command}


def test_version_prints_name_and_number() -> None:
    result = CliRunner().invoke(byte_census_main, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == "byte-census 2.0.0"


def test_bare_invocation_shows_help_and_exits_zero() -> None:
    result = CliRunner().invoke(byte_census_main, [])

    assert result.exit_code == 0
    assert result.output.startswith("Usage:")


@pytest.mark.parametrize("name", sorted(COMMANDS))
@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_flags_start_with_usage_and_have_example(name: str, flag: str) -> None:
    result = CliRunner().invoke(COMMANDS[name], [flag])

    assert result.exit_code == 0
    assert result.output.startswith("Usage:")
    assert "Example:" in result.output
