"""Typed errors, their exit codes, and the JSON error object on stderr.

Exit codes (envelope.md): 1 internal error, 2 argument misuse, 3 validation
error, 4 source unavailable. `to_byte_census_error` maps every exception a
command can raise onto this hierarchy, so there is exactly one error path.
"""

import json
from typing import ClassVar, TextIO

import click

from byte_census.model import EXIT_CODES, ErrorInfo
from byte_census.paths import PathValidationError
from byte_census.runner import (
    CommandLaunchError,
    CommandTimeoutError,
    ExecutableNotFoundError,
    RunnerError,
)

TOOL_HELP = "byte-census --help"


class ByteCensusError(Exception):
    """Base class; `error`, `reason`, and `suggestion` follow ADR-002 S-04."""

    code: ClassVar[str] = "internal_error"

    def __init__(
        self, error: str, reason: str, suggestion: str, help: str | None = None
    ) -> None:
        super().__init__(error)
        self.error = error
        self.reason = reason
        self.suggestion = suggestion
        self.help = help

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.code]

    def info(self, help_hint: str = TOOL_HELP) -> ErrorInfo:
        """The error object; an explicit `help` wins over the caller's hint."""
        return ErrorInfo(
            error=self.error,
            reason=self.reason,
            suggestion=self.suggestion,
            help=self.help or help_hint,
            exit_code=self.exit_code,
        )


class InternalError(ByteCensusError):
    """Exit 1: an unexpected failure inside byte-census."""

    code = "internal_error"


class ArgumentUsageError(ByteCensusError):
    """Exit 2: argument misuse detected by the parser."""

    code = "usage_error"


class ValidationError(ByteCensusError):
    """Exit 3: arguments parse but fail validation."""

    code = "validation_error"


class SourceUnavailableError(ByteCensusError):
    """Exit 4: a source the command cannot work without is unavailable."""

    code = "source_unavailable"


_RUNNER_FIXES = {
    "not_installed": "Install {tool} or add it to PATH, then run the command again.",
    "timed_out": "Check that {tool} responds, then run the command again.",
    "failed": "Check that {tool} can start in this environment, then try again.",
}


def _from_usage(error: click.UsageError) -> ArgumentUsageError:
    path = error.ctx.command_path if error.ctx is not None else "byte-census"
    return ArgumentUsageError(
        error=f"{path} was called with invalid arguments",
        reason=error.format_message(),
        suggestion=f"Run `{path} --help` to see the valid options and arguments.",
        help=f"{path} --help",
    )


def _from_path(error: PathValidationError) -> ValidationError:
    return ValidationError(
        error=f"invalid path argument: {error.path!r}",
        reason=str(error),
        suggestion="Pass an existing directory whose name has no control characters.",
    )


def _from_runner(error: RunnerError) -> SourceUnavailableError:
    tool = error.argv[0] if error.argv else "the command"
    return SourceUnavailableError(
        error=f"`{' '.join(map(str, error.argv))}` could not run",
        reason=str(error),
        suggestion=_RUNNER_FIXES[error.reason].format(tool=tool),
    )


def _internal(error: BaseException) -> InternalError:
    if isinstance(error, (click.Abort, KeyboardInterrupt)):
        return InternalError(
            error="byte-census was interrupted",
            reason="The command stopped before it finished.",
            suggestion="Run the command again and let it finish.",
        )
    return InternalError(
        error="byte-census stopped because of an unexpected internal error",
        reason=f"{type(error).__name__}: {error}",
        suggestion="Run the command again; if it fails the same way, report it "
        "with the command line and this message.",
    )


def to_byte_census_error(error: BaseException) -> ByteCensusError:
    """Map any exception to the typed hierarchy."""
    if isinstance(error, ByteCensusError):
        return error
    if isinstance(error, click.UsageError):
        return _from_usage(error)
    if isinstance(error, PathValidationError):
        return _from_path(error)
    unavailable = (ExecutableNotFoundError, CommandTimeoutError, CommandLaunchError)
    if isinstance(error, unavailable):
        return _from_runner(error)
    return _internal(error)


def emit_error(info: ErrorInfo, stream: TextIO) -> None:
    """Write the error object as one JSON line."""
    stream.write(json.dumps(info.to_dict(), ensure_ascii=False) + "\n")
    stream.flush()
