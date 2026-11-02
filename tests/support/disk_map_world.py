"""Fixture world for `disk map` tests.

tmp_path plays the data volume: its mount path and st_dev are injected, the
home folder lives inside it, and every external command is answered by
`FakeRunner`, which records each argv. Nothing touches the real home, and
df, diskutil, tmutil, docker, uv, and brew never run. Expected totals are
computed independently from `os.walk` and `lstat`.
"""

import json
import os
import stat
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from byte_census import fsread, runner
from byte_census.checks import disk_map
from byte_census.checks.disk_map import DataVolume, DiskMapEnvironment
from byte_census.cli import main

MIB = 1024 * 1024
DF_ARGV = ("df", "-k", "/System/Volumes/Data")
SYSTEM_DF_ARGV = ("df", "-k", "/")
DISKUTIL_ARGV = ("diskutil", "info", "/")
TMUTIL_ARGV = ("tmutil", "listlocalsnapshots", "/")
DOCKER_ARGV = ("docker", "system", "df", "--format", "{{json .}}")
UV_ARGV = ("uv", "cache", "dir")
BREW_ARGV = ("brew", "--cache")
DF_HEADER = (
    "Filesystem    1024-blocks      Used Available Capacity iused ifree %iused"
    "  Mounted on\n"
)
DISKUTIL_TEXT = (
    "   Device Identifier:         disk3s1s1\n"
    "   Volume Name:               Macintosh HD\n"
    "   File System Personality:   APFS\n"
    "   Container Total Space:     994.7 GB (994662584320 Bytes)\n"
    "   Container Free Space:      350.1 GB (350108332032 Bytes)\n"
)
TMUTIL_TEXT = (
    "Snapshots for disk /:\n"
    "com.apple.TimeMachine.2026-11-01-120000.local\n"
    "com.apple.TimeMachine.2026-11-02-080000.local\n"
)
DOCKER_TEXT = (
    '{"Type":"Images","TotalCount":"3","Size":"7.42GB","Reclaimable":"1GB (13%)"}\n'
    '{"Type":"Build Cache","TotalCount":"9","Size":"4.3646GB","Reclaimable":"0B"}\n'
)


def df_output(used_kb: int, total_kb: int = 971350180, mount: str = "") -> str:
    target = mount or "/System/Volumes/Data"
    available = total_kb - used_kb
    return (
        DF_HEADER + f"/dev/disk3s5 {total_kb} {used_kb} {available} 33% 1 2 0%"
        f"   {target}\n"
    )


Answer = str | Exception | tuple[int, str, str]


def _not_installed(argv: tuple[str, ...]) -> Exception:
    return runner.ExecutableNotFoundError(argv, f"{argv[0]} is not installed")


@dataclass
class FakeRunner:
    """Answers each allowlisted argv; records every call in order."""

    answers: dict[tuple[str, ...], Answer] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    stdout_bytes_returned: int = 0

    def __post_init__(self) -> None:
        defaults: dict[tuple[str, ...], Answer] = {
            DF_ARGV: df_output(10**6),
            SYSTEM_DF_ARGV: df_output(11977488, mount="/"),
            DISKUTIL_ARGV: DISKUTIL_TEXT,
            TMUTIL_ARGV: TMUTIL_TEXT,
        }
        self.answers = {**defaults, **self.answers}

    def __call__(self, argv: Sequence[str]) -> runner.RunResult:
        key = tuple(argv)
        self.calls.append(key)
        answer = self.answers[key] if key in self.answers else _not_installed(key)
        if isinstance(answer, Exception):
            raise answer
        code, stdout, stderr = answer if isinstance(answer, tuple) else (0, answer, "")
        self.stdout_bytes_returned += len(stdout.encode())
        return runner.RunResult(
            argv=key,
            executable="/fake/" + key[0],
            returncode=code,
            stdout=stdout,
            stderr=stderr,
            stdout_bytes=len(stdout.encode()),
        )


@dataclass
class World:
    data: Path
    home: Path
    runner: FakeRunner
    lstat: Callable[[str], Any] = fsread.lstat
    categories: tuple[Any, ...] | None = None

    def environment(self) -> DiskMapEnvironment:
        volume = DataVolume(str(self.data), os.lstat(self.data).st_dev)
        environ = {"HOME": str(self.home), "PATH": "/nonexistent"}
        return DiskMapEnvironment(
            volume,
            str(self.home),
            self.runner,
            self.lstat,
            environ=environ,
            categories=self.categories,
        )


def new_world(tmp_path: Path) -> World:
    data = tmp_path.resolve() / "data"
    home = data / "Users" / "example"
    home.mkdir(parents=True)
    return World(data, home, FakeRunner())


def make_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def make_sparse(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


def inodes_under(*paths: Path) -> dict[tuple[int, int], os.stat_result]:
    """Every distinct inode under the given trees, roots included."""
    found: dict[tuple[int, int], os.stat_result] = {}
    for top in paths:
        info = os.lstat(top)
        found[(info.st_dev, info.st_ino)] = info
        for dirpath, dirnames, filenames in os.walk(top):
            for name in dirnames + filenames:
                info = os.lstat(Path(dirpath) / name)
                found[(info.st_dev, info.st_ino)] = info
    return found


def expected_allocated(*paths: Path) -> int:
    return sum(i.st_blocks * 512 for i in inodes_under(*paths).values())


def expected_logical(*paths: Path) -> int:
    return sum(
        i.st_size for i in inodes_under(*paths).values() if stat.S_ISREG(i.st_mode)
    )


def install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    monkeypatch.setattr(disk_map, "default_environment", world.environment)


def run_map(
    monkeypatch: pytest.MonkeyPatch, world: World, roots: Iterable[Path], *args: str
) -> tuple[Result, dict[str, Any]]:
    install(monkeypatch, world)
    argv = ["disk", "map"]
    for root in roots:
        argv += ["--scan-root", str(root)]
    result = CliRunner().invoke(main, [*argv, *args])
    payload = json.loads(result.stdout) if result.stdout else {}
    return result, payload


def findings_of(payload: dict[str, Any], kind: str) -> dict[str, dict[str, Any]]:
    return {f["target"]: f for f in payload["data"]["findings"] if f["kind"] == kind}


class OtherDevice:
    """An lstat result whose st_dev differs from its real device."""

    def __init__(self, info: Any) -> None:
        self._info = info

    def __getattr__(self, name: str) -> Any:
        if name == "st_dev":
            return self._info.st_dev + 1
        return getattr(self._info, name)
