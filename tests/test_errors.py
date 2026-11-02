"""Typed errors and their exit codes (WI-CORE AC-04, AC-05)."""

import io
import json

import click
import pytest

from byte_census import errors
from byte_census.errors import (
    ArgumentUsageError,
    ByteCensusError,
    InternalError,
    SourceUnavailableError,
    ValidationError,
    emit_error,
    to_byte_census_error,
)
from byte_census.paths import PathValidationError
from byte_census.runner import (
    CommandLaunchError,
    CommandTimeoutError,
    ExecutableNotFoundError,
    OutputTooLargeError,
    RejectedArgvError,
    UntrustedExecutableError,
)

DOCKER = ("docker", "system", "df", "--format", "{{json .}}")
HELP = "byte-census docker scan --help"


@pytest.mark.parametrize(
    ("cls", "exit_code", "code"),
    [
        (InternalError, 1, "internal_error"),
        (ArgumentUsageError, 2, "usage_error"),
        (ValidationError, 3, "validation_error"),
        (SourceUnavailableError, 4, "source_unavailable"),
    ],
)
def test_error_classes_map_to_exit_codes(
    cls: type[ByteCensusError], exit_code: int, code: str
) -> None:
    error = cls("what", "why", "fix")

    info = error.info(HELP)

    assert error.exit_code == exit_code
    assert info.code == code
    assert info.to_dict()["help"] == HELP
    assert issubclass(cls, ByteCensusError)


def test_explicit_help_wins_over_hint() -> None:
    info = ValidationError("w", "r", "s", help="custom --help").info(HELP)

    assert info.help == "custom --help"


def test_path_validation_error_maps_to_3() -> None:
    source = PathValidationError("/nope", "not_found", "path does not exist: /nope")

    mapped = to_byte_census_error(source)

    assert isinstance(mapped, ValidationError)
    assert mapped.exit_code == 3
    assert "/nope" in mapped.error
    assert mapped.reason == "path does not exist: /nope"


@pytest.mark.parametrize(
    "source",
    [
        ExecutableNotFoundError(DOCKER, "docker is not installed"),
        CommandTimeoutError(DOCKER, "docker timed out after 120 s", 120),
        CommandLaunchError(DOCKER, "docker could not start: denied"),
        UntrustedExecutableError(DOCKER, "docker resolved to a relative path"),
        OutputTooLargeError(DOCKER, "stdout", 16),
    ],
)
def test_runner_unavailability_maps_to_4(source: Exception) -> None:
    mapped = to_byte_census_error(source)

    assert isinstance(mapped, SourceUnavailableError)
    assert mapped.exit_code == 4
    assert "docker system df" in mapped.error
    assert mapped.reason == str(source)


def test_rejected_argv_is_an_internal_error() -> None:
    mapped = to_byte_census_error(RejectedArgvError(("rm", "-rf"), "not allowed"))

    assert isinstance(mapped, InternalError)
    assert mapped.exit_code == 1


def test_click_usage_error_maps_to_2_with_command_help() -> None:
    command = click.Command("scan")
    ctx = click.Context(command, info_name="byte-census docker scan")
    source = click.UsageError("No such option: --bogus", ctx=ctx)

    mapped = to_byte_census_error(source)
    info = mapped.info("ignored --help")

    assert isinstance(mapped, ArgumentUsageError)
    assert mapped.reason == "No such option: --bogus"
    assert info.help == HELP


def test_click_usage_error_without_context_uses_tool_help() -> None:
    mapped = to_byte_census_error(click.UsageError("bad"))

    assert mapped.info("byte-census --help").help == "byte-census --help"


def test_abort_is_an_internal_interruption() -> None:
    mapped = to_byte_census_error(click.Abort())

    assert isinstance(mapped, InternalError)
    assert "interrupted" in mapped.error


def test_unexpected_exception_is_internal_without_traceback() -> None:
    mapped = to_byte_census_error(KeyError("boom"))

    assert isinstance(mapped, InternalError)
    assert "KeyError" in mapped.reason
    assert "Traceback" not in mapped.reason


def test_byte_census_error_passes_through_unchanged() -> None:
    original = SourceUnavailableError("w", "r", "s")

    assert to_byte_census_error(original) is original


def test_emit_error_writes_one_json_object() -> None:
    stream = io.StringIO()

    emit_error(SourceUnavailableError("w", "r", "s").info(HELP), stream)

    text = stream.getvalue()
    assert text.endswith("\n")
    assert json.loads(text) == {
        "schema_version": "1.0.0",
        "error": "w",
        "reason": "r",
        "suggestion": "s",
        "help": HELP,
        "code": "source_unavailable",
        "exit_code": 4,
    }


def test_module_exports_exit_code_table() -> None:
    assert errors.EXIT_CODES == {
        "internal_error": 1,
        "usage_error": 2,
        "validation_error": 3,
        "source_unavailable": 4,
    }


class OddSignatureError(SourceUnavailableError):
    def __init__(self, only: str) -> None:
        super().__init__("odd " + only, "r", "s")


def test_with_help_copies_without_calling_init() -> None:
    original = OddSignatureError("x")

    copy = original.with_help("byte-census docker scan --help")

    assert type(copy) is OddSignatureError
    assert copy is not original
    assert original.help is None
    assert copy.help == "byte-census docker scan --help"
    assert (copy.error, copy.reason, copy.suggestion) == ("odd x", "r", "s")
    assert copy.exit_code == 4
    assert str(copy) == str(original)


def test_with_help_keeps_an_existing_help() -> None:
    original = ValidationError("w", "r", "s", help="mine --help")

    assert original.with_help("other --help") is original


def test_usage_error_for_path_builds_the_message() -> None:
    error = errors.usage_error(
        "byte-census disk map", "Option '--top' requires an argument."
    )

    assert error.info().help == "byte-census disk map --help"
    assert error.error == "byte-census disk map was called with invalid arguments"
