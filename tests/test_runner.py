"""Tests for the process gateway (WI-SAFETY AC-01, AC-02).

Every test injects a fake Popen-style launcher, a fake `which`, and a fake
`killpg`, so no real docker, npm, brew, tmutil, or other external command
ever runs and no real process group is signalled.
"""

import dataclasses
import os
import signal
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from byte_census import runner
from byte_census.runner import (
    CommandLaunchError,
    CommandTimeoutError,
    ExecutableNotFoundError,
    OutputTooLargeError,
    RejectedArgvError,
    RunResult,
    UntrustedExecutableError,
    run,
)

CONTRACT_ARGVS = [
    ["docker", "system", "df", "--format", "{{json .}}"],
    ["docker", "images", "--format", "{{json .}}"],
    ["docker", "images", "-f", "dangling=true", "-q"],
    ["docker", "ps", "-a", "-f", "status=exited", "--format", "{{json .}}"],
    ["uv", "cache", "dir"],
    ["npm", "config", "get", "cache"],
    ["brew", "--cache"],
    ["df", "-k", "/"],
    ["df", "-k", "/System/Volumes/Data"],
    ["diskutil", "info", "/"],
    ["tmutil", "listlocalsnapshots", "/"],
]

EXPECTED_TIMEOUTS = {
    "docker": 120,
    "uv": 60,
    "npm": 60,
    "brew": 60,
    "df": 60,
    "diskutil": 60,
    "tmutil": 60,
}

PINNED = {
    "df": "/bin/df",
    "diskutil": "/usr/sbin/diskutil",
    "tmutil": "/usr/bin/tmutil",
}


def _pipe(data: bytes, close_writer: bool = True) -> Any:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, data)
    if close_writer:
        os.close(write_fd)
    return os.fdopen(read_fd, "rb"), (None if close_writer else write_fd)


class FakeProcess:
    """Popen stand-in backed by real pipes, so the runner's reader is exercised."""

    def __init__(
        self, stdout: bytes, stderr: bytes, returncode: int, hang: bool
    ) -> None:
        self.pid = 4242
        self.stdout, self._out_writer = _pipe(stdout, close_writer=not hang)
        self.stderr, self._err_writer = _pipe(stderr)
        self.returncode = returncode
        self.waited = 0

    def wait(self, timeout: float | None = None) -> int:
        self.waited += 1
        return self.returncode

    def release(self) -> None:
        if self._out_writer is not None:
            os.close(self._out_writer)


class FakeLauncher:
    """Records each call and returns a FakeProcess, or raises."""

    def __init__(
        self,
        stdout: bytes = b"out\n",
        stderr: bytes = b"",
        returncode: int = 0,
        error: Exception | None = None,
        hang: bool = False,
    ) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.processes: list[FakeProcess] = []
        self._spec = (stdout, stderr, returncode, hang)
        self._error = error

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> FakeProcess:
        self.calls.append((list(argv), kwargs))
        if self._error is not None:
            raise self._error
        process = FakeProcess(*self._spec)
        self.processes.append(process)
        return process


class FakeKillpg:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def __call__(self, pid: int, sig: int) -> None:
        self.calls.append((pid, sig))


def fake_which(name: str) -> str | None:
    return f"/fake/bin/{name}"


def missing_which(name: str) -> None:
    return None


def call(argv: list[str], launcher: FakeLauncher | None = None, **kwargs: Any) -> Any:
    options = {"which": fake_which, "environ": {}, "killpg": FakeKillpg(), **kwargs}
    return run(argv, launcher=launcher or FakeLauncher(), **options)


def expected_executable(name: str) -> str:
    return PINNED.get(name, f"/fake/bin/{name}")


@pytest.mark.parametrize("argv", CONTRACT_ARGVS, ids=" ".join)
def test_every_contract_row_is_accepted(argv: list[str]) -> None:
    launcher = FakeLauncher()

    result = call(argv, launcher)

    assert result.returncode == 0
    assert len(launcher.calls) == 1
    called_argv, kwargs = launcher.calls[0]
    assert called_argv == [expected_executable(argv[0]), *argv[1:]]
    assert kwargs["shell"] is False
    assert kwargs["cwd"] == "/"
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE


@pytest.mark.parametrize("argv", CONTRACT_ARGVS, ids=" ".join)
def test_every_row_has_its_contract_timeout(argv: list[str]) -> None:
    assert runner.match_template(argv).timeout_s == EXPECTED_TIMEOUTS[argv[0]]


def test_allowlist_matches_contract_table_exactly() -> None:
    assert sorted(list(spec.argv) for spec in runner.ALLOWED_COMMANDS) == sorted(
        CONTRACT_ARGVS
    )


REJECTED = [
    ["docker", "system", "prune"],
    ["docker", "system", "prune", "-a"],
    ["docker", "images", "--filter", "dangling=true", "-q"],
    ["docker", "images", "-f", "dangling=false", "-q"],
    ["docker", "images", "-f", "reference=foo", "--format", "{{json .}}"],
    ["docker", "images", "--format", "{{json .}}", "--all"],
    ["docker", "ps", "-a", "-f", "status=exited", "--format", "{{json .}}", "-q"],
    ["uv", "cache", "dir", "extra"],
    ["uv", "cache", "prune"],
    ["brew", "--cache", "--verbose"],
    ["brew", "cleanup"],
    ["npm", "cache", "verify"],
    ["df", "-k", "/Users"],
    ["df", "-k", "/", "/System/Volumes/Data"],
    ["df", "-h", "/"],
    ["df", "-k"],
    ["du", "-sk", "/"],
    ["find", "/", "-xdev"],
    ["sh", "-c", "docker system df"],
    ["docker system df --format {{json .}}"],
    ["uv", "cache", "dir;", "rm", "-rf", "/"],
    ["uv", "cache", "dir && rm -rf /"],
    ["df", "-k", "/ | cat"],
    ["df", "-k", "$(whoami)"],
    ["/usr/bin/df", "-k", "/"],
    [],
]


@pytest.mark.parametrize("argv", REJECTED, ids=repr)
def test_argv_outside_table_is_rejected_before_launch(argv: list[str]) -> None:
    launcher = FakeLauncher()

    with pytest.raises(RejectedArgvError):
        call(argv, launcher)

    assert launcher.calls == []


def test_docker_system_prune_is_rejected() -> None:
    with pytest.raises(RejectedArgvError, match="not in the allowlist"):
        call(["docker", "system", "prune"])


def test_non_string_tokens_are_rejected() -> None:
    with pytest.raises(RejectedArgvError):
        call(["df", "-k", b"/"])  # type: ignore[list-item]


def test_string_argv_is_rejected() -> None:
    with pytest.raises(RejectedArgvError):
        call("uv cache dir")  # type: ignore[arg-type]


# H1: executable resolution cannot be hijacked through PATH.


def _plant(directory: Path, name: str) -> Path:
    script = directory / name
    script.write_text("#!/bin/sh\necho planted\n")
    script.chmod(0o755)
    return script


@pytest.mark.parametrize("name", ["df", "diskutil", "tmutil"])
def test_system_tools_are_pinned_and_never_looked_up(name: str) -> None:
    looked_up: list[str] = []

    def which(tool: str) -> str:
        looked_up.append(tool)
        return f"/evil/{tool}"

    argv = next(a for a in CONTRACT_ARGVS if a[0] == name)
    launcher = FakeLauncher()
    call(argv, launcher, which=which)

    assert looked_up == []
    assert launcher.calls[0][0][0] == PINNED[name]


def test_relative_which_result_is_rejected() -> None:
    launcher = FakeLauncher()

    with pytest.raises(UntrustedExecutableError) as caught:
        call(["uv", "cache", "dir"], launcher, which=lambda name: name)

    assert caught.value.reason == "failed"
    assert launcher.calls == []


def test_empty_path_entry_cannot_run_planted_executables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for name in ("df", "docker", "uv", "npm", "brew"):
        _plant(tmp_path, name)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "/nonexistent::/bin")
    launcher = FakeLauncher()

    call(["df", "-k", "/"], launcher, which=runner.shutil.which)
    for argv in (
        ["docker", "images", "-f", "dangling=true", "-q"],
        ["uv", "cache", "dir"],
    ):
        with pytest.raises((UntrustedExecutableError, ExecutableNotFoundError)):
            call(argv, launcher, which=runner.shutil.which)

    launched = [argv[0] for argv, _ in launcher.calls]
    assert launched == ["/bin/df"]
    assert all(not exe.startswith(str(tmp_path)) for exe in launched)


def test_which_result_is_resolved_with_realpath(tmp_path: Path) -> None:
    real = _plant(tmp_path, "real-brew")
    link = tmp_path / "brew"
    link.symlink_to(real)
    launcher = FakeLauncher()

    call(["brew", "--cache"], launcher, which=lambda name: str(link))

    assert launcher.calls[0][0][0] == os.path.realpath(real)


# H2: children get a minimal, explicit environment.

USER_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/Users/someone",
    "USER": "someone",
    "TMPDIR": "/tmp/x/",
    "LC_ALL": "de_DE.UTF-8",
    "LANG": "de_DE.UTF-8",
    "AWS_SECRET_ACCESS_KEY": "secret",
    "NODE_OPTIONS": "--require /tmp/evil.js",
    "npm_config_logs_dir": "/tmp/logs",
    "npm_config_cache": "/custom/npm",
    "UV_CACHE_DIR": "/custom/uv",
    "XDG_CACHE_HOME": "/custom/xdg",
    "HOMEBREW_CACHE": "/custom/brew",
    "DOCKER_HOST": "unix:///custom.sock",
    "DOCKER_CONTEXT": "colima",
    "DOCKER_CONFIG": "/custom/docker",
}

BASE_ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/Users/someone",
    "USER": "someone",
    "TMPDIR": "/tmp/x/",
    "LC_ALL": "C",
}


def child_env(argv: list[str]) -> dict[str, str]:
    launcher = FakeLauncher()
    call(argv, launcher, environ=USER_ENV)
    return launcher.calls[0][1]["env"]


def test_npm_environment_disables_log_files_and_update_checks() -> None:
    assert child_env(["npm", "config", "get", "cache"]) == {
        **BASE_ENV,
        "npm_config_cache": "/custom/npm",
        "npm_config_logs_max": "0",
        "npm_config_update_notifier": "false",
    }


def test_brew_environment_disables_updates_analytics_and_hints() -> None:
    assert child_env(["brew", "--cache"]) == {
        **BASE_ENV,
        "HOMEBREW_CACHE": "/custom/brew",
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        "HOMEBREW_NO_ANALYTICS": "1",
        "HOMEBREW_NO_ENV_HINTS": "1",
    }


def test_uv_environment_keeps_only_cache_location_variables() -> None:
    assert child_env(["uv", "cache", "dir"]) == {
        **BASE_ENV,
        "UV_CACHE_DIR": "/custom/uv",
        "XDG_CACHE_HOME": "/custom/xdg",
    }


def test_docker_environment_keeps_only_connection_variables() -> None:
    assert child_env(["docker", "images", "-f", "dangling=true", "-q"]) == {
        **BASE_ENV,
        "DOCKER_HOST": "unix:///custom.sock",
        "DOCKER_CONTEXT": "colima",
        "DOCKER_CONFIG": "/custom/docker",
        "DOCKER_CLI_HINTS": "false",
    }


@pytest.mark.parametrize(
    "argv",
    [
        ["df", "-k", "/"],
        ["diskutil", "info", "/"],
        ["tmutil", "listlocalsnapshots", "/"],
    ],
)
def test_system_tool_environment_is_the_base(argv: list[str]) -> None:
    assert child_env(argv) == BASE_ENV


def test_missing_variables_are_not_invented() -> None:
    launcher = FakeLauncher()

    call(["brew", "--cache"], launcher, environ={})

    assert launcher.calls[0][1]["env"] == {
        "LC_ALL": "C",
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        "HOMEBREW_NO_ANALYTICS": "1",
        "HOMEBREW_NO_ENV_HINTS": "1",
    }


def test_default_environment_comes_from_the_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", "/home/test")
    monkeypatch.setenv("SECRET_TOKEN", "x")
    launcher = FakeLauncher()

    run(
        ["uv", "cache", "dir"], launcher=launcher, which=fake_which, killpg=FakeKillpg()
    )

    env = launcher.calls[0][1]["env"]
    assert env["HOME"] == "/home/test"
    assert "SECRET_TOKEN" not in env


# Results and errors.


def test_result_is_immutable_and_reports_stdout_bytes() -> None:
    launcher = FakeLauncher("café\n".encode(), b"warn", 3)

    result = call(["brew", "--cache"], launcher)

    assert isinstance(result, RunResult)
    assert result.argv == ("brew", "--cache")
    assert result.executable == "/fake/bin/brew"
    assert result.returncode == 3
    assert result.ok is False
    assert result.stdout == "café\n"
    assert result.stderr == "warn"
    assert result.stdout_bytes == 6
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.returncode = 0  # type: ignore[misc]


def test_ok_is_true_for_zero_exit() -> None:
    assert call(["uv", "cache", "dir"]).ok is True


def test_large_output_within_the_cap_is_read_completely() -> None:
    data = b"x" * 50_000
    result = call(
        ["uv", "cache", "dir"], FakeLauncher(stdout=data, stderr=b"e" * 30_000)
    )

    assert result.stdout_bytes == 50_000
    assert len(result.stderr) == 30_000


def test_missing_executable_raises_not_installed() -> None:
    launcher = FakeLauncher()

    with pytest.raises(ExecutableNotFoundError) as caught:
        call(
            ["docker", "images", "--format", "{{json .}}"],
            launcher,
            which=missing_which,
        )

    assert caught.value.reason == "not_installed"
    assert caught.value.argv == ("docker", "images", "--format", "{{json .}}")
    assert launcher.calls == []


def test_launch_os_error_raises_typed_error() -> None:
    launcher = FakeLauncher(error=PermissionError(13, "Permission denied"))

    with pytest.raises(CommandLaunchError) as caught:
        call(["diskutil", "info", "/"], launcher)

    assert caught.value.reason == "failed"


def test_vanished_executable_maps_to_not_installed() -> None:
    launcher = FakeLauncher(error=FileNotFoundError(2, "No such file"))

    with pytest.raises(ExecutableNotFoundError):
        call(["npm", "config", "get", "cache"], launcher)


# L1: process groups, timeouts, and output caps.


class SteppingClock:
    """Monotonic clock that advances by `step` seconds on every reading."""

    def __init__(self, step: float) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        current = self.now
        self.now += self.step
        return current


def test_timeout_kills_the_whole_process_group() -> None:
    launcher = FakeLauncher(hang=True)
    killpg = FakeKillpg()

    with pytest.raises(CommandTimeoutError) as caught:
        call(
            ["tmutil", "listlocalsnapshots", "/"],
            launcher,
            killpg=killpg,
            clock=SteppingClock(1000.0),
        )

    launcher.processes[0].release()
    assert caught.value.reason == "timed_out"
    assert caught.value.timeout_s == 60
    assert killpg.calls == [(4242, signal.SIGKILL)]
    assert launcher.processes[0].waited >= 1


def test_wait_timeout_after_output_kills_the_group() -> None:
    class SlowExit(FakeLauncher):
        def __call__(self, argv: Sequence[str], **kwargs: Any) -> FakeProcess:
            process = super().__call__(argv, **kwargs)

            def wait(timeout: float | None = None) -> int:
                if timeout is not None:
                    raise subprocess.TimeoutExpired(argv, timeout)
                return 0

            process.wait = wait  # type: ignore[method-assign]
            return process

    killpg = FakeKillpg()

    with pytest.raises(CommandTimeoutError):
        call(["uv", "cache", "dir"], SlowExit(), killpg=killpg)

    assert killpg.calls == [(4242, signal.SIGKILL)]


def test_kill_of_an_already_gone_group_is_tolerated() -> None:
    def gone(pid: int, sig: int) -> None:
        raise ProcessLookupError(3, "No such process")

    launcher = FakeLauncher(hang=True)

    with pytest.raises(CommandTimeoutError):
        call(["uv", "cache", "dir"], launcher, killpg=gone, clock=SteppingClock(1000.0))

    launcher.processes[0].release()


def test_stdout_over_the_cap_raises_and_kills_the_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner, "MAX_STDOUT_BYTES", 10)
    killpg = FakeKillpg()

    with pytest.raises(OutputTooLargeError) as caught:
        call(["uv", "cache", "dir"], FakeLauncher(stdout=b"y" * 100), killpg=killpg)

    assert caught.value.reason == "failed"
    assert caught.value.stream == "stdout"
    assert caught.value.limit == 10
    assert killpg.calls == [(4242, signal.SIGKILL)]


def test_stderr_over_the_cap_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "MAX_STDERR_BYTES", 5)

    with pytest.raises(OutputTooLargeError) as caught:
        call(["uv", "cache", "dir"], FakeLauncher(stderr=b"z" * 50))

    assert caught.value.stream == "stderr"


def test_pipes_are_closed_after_the_run() -> None:
    launcher = FakeLauncher()

    call(["uv", "cache", "dir"], launcher)

    process = launcher.processes[0]
    assert process.stdout.closed
    assert process.stderr.closed


def test_all_errors_share_a_base_class() -> None:
    for error_type in (
        RejectedArgvError,
        ExecutableNotFoundError,
        UntrustedExecutableError,
        CommandTimeoutError,
        CommandLaunchError,
        OutputTooLargeError,
    ):
        assert issubclass(error_type, runner.RunnerError)


@pytest.mark.skipif(not os.path.exists("/bin/df"), reason="needs /bin/df")
def test_real_popen_path_runs_pinned_df() -> None:
    """df is read-only and pinned; this exercises the real Popen arguments."""
    result = run(["df", "-k", "/"])

    assert result.ok
    assert result.executable == "/bin/df"
    assert result.stdout.startswith("Filesystem")
