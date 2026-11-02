"""The only process gateway in byte-census.

Every external command runs through `run`, which accepts an argv only when it
matches one row of docs/contracts/argv-allowlist.md exactly (see
`byte_census.command_policy`). Children run with `shell=False`, `cwd="/"`, a
minimal explicit environment, stdin closed, and in their own session, so a
timeout or an oversized output kills the whole process group.
"""

import os
import selectors
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from byte_census.command_policy import (
    ALLOWED_COMMANDS,
    PINNED_EXECUTABLES,
    TEMPLATES,
    CommandSpec,
    CommandTemplate,
    child_environment,
    find_template,
    is_string_argv,
)

__all__ = [
    "ALLOWED_COMMANDS",
    "TEMPLATES",
    "CommandSpec",
    "CommandTemplate",
    "RunResult",
    "match_template",
    "run",
]

MAX_STDOUT_BYTES = 16 * 1024 * 1024
MAX_STDERR_BYTES = 1024 * 1024
READ_SIZE = 64 * 1024
CHILD_CWD = "/"


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


class UntrustedExecutableError(RunnerError):
    """PATH lookup returned a relative path, which could be a planted file."""

    reason = "failed"


class CommandTimeoutError(RunnerError):
    """The command did not finish within its timeout."""

    reason = "timed_out"

    def __init__(self, argv: Sequence[str], message: str, timeout_s: int) -> None:
        super().__init__(argv, message)
        self.timeout_s = timeout_s


class CommandLaunchError(RunnerError):
    """The operating system refused to start the command."""

    reason = "failed"


class OutputTooLargeError(RunnerError):
    """A captured stream exceeded its size cap; the command was killed."""

    reason = "failed"

    def __init__(self, argv: Sequence[str], stream: str, limit: int) -> None:
        super().__init__(argv, f"{argv[0]} {stream} exceeded {limit} bytes")
        self.stream = stream
        self.limit = limit


class _DeadlineExceeded(Exception):
    """Internal signal that the read loop ran out of time."""


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


class _Process(Protocol):
    pid: int
    stdout: Any
    stderr: Any

    def wait(self, timeout: float | None = None) -> int: ...


Launcher = Callable[..., _Process]
Which = Callable[[str], str | None]
KillPg = Callable[[int, int], None]
Clock = Callable[[], float]


def match_template(argv: Sequence[Any]) -> CommandTemplate:
    """Return the allowlist row argv matches, or raise RejectedArgvError."""
    if not is_string_argv(argv):
        shown = (argv,) if isinstance(argv, (str, bytes)) else tuple(argv)
        raise RejectedArgvError(shown, "argv must be a sequence of strings")
    template = find_template(argv)
    if template is None:
        raise RejectedArgvError(argv, f"argv is not in the allowlist: {list(argv)!r}")
    return template


def resolve_executable(argv: tuple[str, ...], which: Which) -> str:
    """Return the absolute, resolved executable for argv[0]."""
    name = argv[0]
    if name in PINNED_EXECUTABLES:
        return PINNED_EXECUTABLES[name]
    found = which(name)
    if found is None:
        raise ExecutableNotFoundError(argv, f"{name} is not installed")
    if not os.path.isabs(found):
        raise UntrustedExecutableError(
            argv, f"{name} resolved to a relative path {found!r}; refusing to run it"
        )
    return os.path.realpath(found)


def run(
    argv: Sequence[str],
    *,
    launcher: Launcher = subprocess.Popen,
    which: Which = shutil.which,
    environ: Mapping[str, str] | None = None,
    killpg: KillPg = os.killpg,
    clock: Clock = time.monotonic,
) -> RunResult:
    """Run one allowlisted command and return its captured output.

    Raises RejectedArgvError, ExecutableNotFoundError, UntrustedExecutableError,
    CommandLaunchError, CommandTimeoutError, or OutputTooLargeError. A nonzero
    exit is returned, not raised; callers record it with reason `failed`.
    """
    template = match_template(argv)
    key = tuple(argv)
    executable = resolve_executable(key, which)
    env = child_environment(key[0], os.environ if environ is None else environ)
    process = _start(launcher, key, [executable, *key[1:]], env)
    stdout, stderr, returncode = _collect(
        process, key, template.timeout_s, killpg, clock
    )
    return RunResult(
        argv=key,
        executable=executable,
        returncode=returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        stdout_bytes=len(stdout),
    )


def _start(
    launcher: Launcher, key: tuple[str, ...], command: list[str], env: dict[str, str]
) -> _Process:
    try:
        return launcher(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            cwd=CHILD_CWD,
            env=env,
            start_new_session=True,
            close_fds=True,
        )
    except FileNotFoundError as error:
        raise ExecutableNotFoundError(key, f"{key[0]} vanished: {error}") from error
    except OSError as error:
        raise CommandLaunchError(key, f"{key[0]} could not start: {error}") from error


def _collect(
    process: _Process,
    key: tuple[str, ...],
    timeout_s: int,
    killpg: KillPg,
    clock: Clock,
) -> tuple[bytes, bytes, int]:
    deadline = clock() + timeout_s
    try:
        stdout, stderr = _drain(process, key, deadline, clock)
        returncode = process.wait(timeout=max(deadline - clock(), 0.0))
    except (_DeadlineExceeded, subprocess.TimeoutExpired) as error:
        _kill_group(process, killpg)
        message = f"{key[0]} timed out after {timeout_s} s"
        raise CommandTimeoutError(key, message, timeout_s) from error
    except OutputTooLargeError:
        _kill_group(process, killpg)
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
    return stdout, stderr, returncode


def _drain(
    process: _Process, key: tuple[str, ...], deadline: float, clock: Clock
) -> tuple[bytes, bytes]:
    """Read both pipes until EOF, enforcing the deadline and the size caps."""
    names = {process.stdout.fileno(): "stdout", process.stderr.fileno(): "stderr"}
    limits = {"stdout": MAX_STDOUT_BYTES, "stderr": MAX_STDERR_BYTES}
    chunks: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
    sizes = {"stdout": 0, "stderr": 0}
    with selectors.DefaultSelector() as selector:
        for fd in names:
            selector.register(fd, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - clock()
            if remaining <= 0:
                raise _DeadlineExceeded
            for ready, _ in selector.select(remaining):
                chunk = os.read(ready.fd, READ_SIZE)
                if not chunk:
                    selector.unregister(ready.fd)
                    continue
                name = names[ready.fd]
                chunks[name].append(chunk)
                sizes[name] += len(chunk)
                if sizes[name] > limits[name]:
                    raise OutputTooLargeError(key, name, limits[name])
    return b"".join(chunks["stdout"]), b"".join(chunks["stderr"])


def _kill_group(process: _Process, killpg: KillPg) -> None:
    """Kill the child's whole session, then reap the child."""
    try:
        killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
