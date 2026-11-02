"""The only process gateway in byte-census.

Every external command runs through `run`, which accepts an argv only when it
matches one row of docs/contracts/argv-allowlist.md exactly: same tokens, same
order, same count, with each variable operand passing its validator. Anything
else is rejected before a process starts.
"""

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class _Operand:
    """A variable argv slot that accepts only the listed constant values."""

    name: str
    allowed: frozenset[str]

    def accepts(self, token: str) -> bool:
        return token in self.allowed


DF_MOUNT_POINT = _Operand("PATH", frozenset({"/", "/System/Volumes/Data"}))
JSON_FORMAT = "{{json .}}"

Token = str | _Operand


@dataclass(frozen=True)
class CommandTemplate:
    """One row of the argv allowlist."""

    tokens: tuple[Token, ...]
    timeout_s: int

    def matches(self, argv: Sequence[str]) -> bool:
        if len(argv) != len(self.tokens):
            return False
        return all(
            token.accepts(value) if isinstance(token, _Operand) else token == value
            for token, value in zip(self.tokens, argv, strict=True)
        )


@dataclass(frozen=True)
class CommandSpec:
    """One concrete argv the allowlist permits, with its timeout."""

    argv: tuple[str, ...]
    timeout_s: int


TEMPLATES: tuple[CommandTemplate, ...] = (
    CommandTemplate(("docker", "system", "df", "--format", JSON_FORMAT), 120),
    CommandTemplate(("docker", "images", "--format", JSON_FORMAT), 120),
    CommandTemplate(("docker", "images", "-f", "dangling=true", "-q"), 120),
    CommandTemplate(
        ("docker", "ps", "-a", "-f", "status=exited", "--format", JSON_FORMAT), 120
    ),
    CommandTemplate(("uv", "cache", "dir"), 60),
    CommandTemplate(("npm", "config", "get", "cache"), 60),
    CommandTemplate(("brew", "--cache"), 60),
    CommandTemplate(("df", "-k", DF_MOUNT_POINT), 60),
    CommandTemplate(("diskutil", "info", "/"), 60),
    CommandTemplate(("tmutil", "listlocalsnapshots", "/"), 60),
)


def _expand(template: CommandTemplate) -> tuple[CommandSpec, ...]:
    """List every concrete argv a template permits."""
    combos: list[tuple[str, ...]] = [()]
    for token in template.tokens:
        values = sorted(token.allowed) if isinstance(token, _Operand) else [token]
        combos = [prefix + (value,) for prefix in combos for value in values]
    return tuple(CommandSpec(argv, template.timeout_s) for argv in combos)


ALLOWED_COMMANDS: tuple[CommandSpec, ...] = tuple(
    spec for template in TEMPLATES for spec in _expand(template)
)


class RunnerError(Exception):
    """Base class for every runner failure."""

    reason = "failed"

    def __init__(self, argv: Sequence[Any], message: str) -> None:
        super().__init__(message)
        self.argv = tuple(argv)


class RejectedArgvError(RunnerError):
    """The argv does not match any row of the allowlist."""

    reason = "rejected"


class ExecutableNotFoundError(RunnerError):
    """The executable for argv[0] is not installed or not on PATH."""

    reason = "not_installed"


class CommandTimeoutError(RunnerError):
    """The command did not finish within its timeout."""

    reason = "timed_out"

    def __init__(self, argv: Sequence[str], message: str, timeout_s: int) -> None:
        super().__init__(argv, message)
        self.timeout_s = timeout_s


class CommandLaunchError(RunnerError):
    """The operating system refused to start the command."""

    reason = "failed"


@dataclass(frozen=True)
class RunResult:
    """Outcome of one allowlisted command."""

    argv: tuple[str, ...]
    executable: str
    returncode: int
    stdout: str
    stderr: str
    stdout_bytes: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class _Completed(Protocol):
    returncode: int
    stdout: bytes
    stderr: bytes


Launcher = Callable[..., _Completed]
Which = Callable[[str], str | None]


def match_template(argv: Sequence[Any]) -> CommandTemplate:
    """Return the allowlist row argv matches, or raise RejectedArgvError."""
    if isinstance(argv, (str, bytes)) or not all(isinstance(t, str) for t in argv):
        raise RejectedArgvError(
            tuple(argv) if not isinstance(argv, (str, bytes)) else (argv,),
            "argv must be a sequence of strings",
        )
    for template in TEMPLATES:
        if template.matches(argv):
            return template
    raise RejectedArgvError(argv, f"argv is not in the allowlist: {list(argv)!r}")


def _child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    return {**environ, "LC_ALL": "C"}


def run(
    argv: Sequence[str],
    *,
    launcher: Launcher = subprocess.run,
    which: Which = shutil.which,
    environ: Mapping[str, str] | None = None,
) -> RunResult:
    """Run one allowlisted command and return its captured output.

    Raises RejectedArgvError, ExecutableNotFoundError, CommandTimeoutError, or
    CommandLaunchError. A nonzero exit is returned, not raised; callers turn it
    into an `unavailable_sources` entry with reason `failed`.
    """
    template = match_template(argv)
    key = tuple(argv)
    executable = which(key[0])
    if executable is None:
        raise ExecutableNotFoundError(key, f"{key[0]} is not installed")
    env = _child_environment(os.environ if environ is None else environ)
    try:
        completed = launcher(
            [executable, *key[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=template.timeout_s,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        message = f"{key[0]} timed out after {template.timeout_s} s"
        raise CommandTimeoutError(key, message, template.timeout_s) from error
    except FileNotFoundError as error:
        raise ExecutableNotFoundError(key, f"{key[0]} vanished: {error}") from error
    except OSError as error:
        raise CommandLaunchError(key, f"{key[0]} could not start: {error}") from error
    return _to_result(key, executable, completed)


def _to_result(
    argv: tuple[str, ...], executable: str, completed: _Completed
) -> RunResult:
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    return RunResult(
        argv=argv,
        executable=executable,
        returncode=completed.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        stdout_bytes=len(stdout),
    )
