"""Tests for the process gateway (WI-SAFETY AC-01, AC-02).

Every test injects a fake launcher and a fake `which`, so no real
docker, brew, tmutil, or other external command ever runs.
"""

import dataclasses
import subprocess
from collections.abc import Sequence
from typing import Any

import pytest

from byte_census import runner
from byte_census.runner import (
    CommandLaunchError,
    CommandTimeoutError,
    ExecutableNotFoundError,
    RejectedArgvError,
    RunResult,
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


@dataclasses.dataclass(frozen=True)
class FakeCompleted:
    returncode: int
    stdout: bytes
    stderr: bytes


class FakeLauncher:
    """Records each call and returns a canned result or raises."""

    def __init__(
        self, result: FakeCompleted | None = None, error: Exception | None = None
    ):
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self._result = result or FakeCompleted(0, b"out\n", b"")
        self._error = error

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> FakeCompleted:
        self.calls.append((list(argv), kwargs))
        if self._error is not None:
            raise self._error
        return self._result


def fake_which(name: str) -> str | None:
    return f"/fake/bin/{name}"


def missing_which(name: str) -> None:
    return None


@pytest.mark.parametrize("argv", CONTRACT_ARGVS, ids=" ".join)
def test_every_contract_row_is_accepted(argv: list[str]) -> None:
    launcher = FakeLauncher()

    result = run(argv, launcher=launcher, which=fake_which, environ={})

    assert result.returncode == 0
    assert len(launcher.calls) == 1
    called_argv, kwargs = launcher.calls[0]
    assert called_argv == [f"/fake/bin/{argv[0]}", *argv[1:]]
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == EXPECTED_TIMEOUTS[argv[0]]
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.PIPE
    assert kwargs["check"] is False


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
        run(argv, launcher=launcher, which=fake_which, environ={})

    assert launcher.calls == []


def test_docker_system_prune_is_rejected() -> None:
    with pytest.raises(RejectedArgvError, match="not in the allowlist"):
        run(["docker", "system", "prune"], launcher=FakeLauncher(), which=fake_which)


def test_non_string_tokens_are_rejected() -> None:
    with pytest.raises(RejectedArgvError):
        run(["df", "-k", b"/"], launcher=FakeLauncher(), which=fake_which)  # type: ignore[list-item]


def test_string_argv_is_rejected() -> None:
    with pytest.raises(RejectedArgvError):
        run("uv cache dir", launcher=FakeLauncher(), which=fake_which)  # type: ignore[arg-type]


def test_environment_is_inherited_with_lc_all_c() -> None:
    launcher = FakeLauncher()

    run(
        ["uv", "cache", "dir"],
        launcher=launcher,
        which=fake_which,
        environ={"PATH": "/x", "LC_ALL": "de_DE.UTF-8"},
    )

    assert launcher.calls[0][1]["env"] == {"PATH": "/x", "LC_ALL": "C"}


def test_result_is_immutable_and_reports_stdout_bytes() -> None:
    launcher = FakeLauncher(FakeCompleted(3, "café\n".encode(), b"warn"))

    result = run(["brew", "--cache"], launcher=launcher, which=fake_which, environ={})

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
    result = run(["uv", "cache", "dir"], launcher=FakeLauncher(), which=fake_which)

    assert result.ok is True


def test_missing_executable_raises_not_installed() -> None:
    launcher = FakeLauncher()

    with pytest.raises(ExecutableNotFoundError) as caught:
        run(
            ["docker", "images", "--format", "{{json .}}"],
            launcher=launcher,
            which=missing_which,
        )

    assert caught.value.reason == "not_installed"
    assert caught.value.argv == ("docker", "images", "--format", "{{json .}}")
    assert launcher.calls == []


def test_timeout_raises_typed_error() -> None:
    launcher = FakeLauncher(error=subprocess.TimeoutExpired(["tmutil"], 60))

    with pytest.raises(CommandTimeoutError) as caught:
        run(["tmutil", "listlocalsnapshots", "/"], launcher=launcher, which=fake_which)

    assert caught.value.reason == "timed_out"
    assert caught.value.timeout_s == 60


def test_launch_os_error_raises_typed_error() -> None:
    launcher = FakeLauncher(error=PermissionError(13, "Permission denied"))

    with pytest.raises(CommandLaunchError) as caught:
        run(["diskutil", "info", "/"], launcher=launcher, which=fake_which)

    assert caught.value.reason == "failed"


def test_vanished_executable_maps_to_not_installed() -> None:
    launcher = FakeLauncher(error=FileNotFoundError(2, "No such file"))

    with pytest.raises(ExecutableNotFoundError):
        run(["npm", "config", "get", "cache"], launcher=launcher, which=fake_which)


def test_all_errors_share_a_base_class() -> None:
    for error_type in (
        RejectedArgvError,
        ExecutableNotFoundError,
        CommandTimeoutError,
        CommandLaunchError,
    ):
        assert issubclass(error_type, runner.RunnerError)
