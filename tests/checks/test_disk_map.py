"""Tests for `byte-census disk map` (WI-DISK-MAP AC-01 to AC-06).

Every tree is built in tmp_path, which plays the data volume: its mount path
and st_dev are injected. `df` runs through a fake runner. Expected totals are
computed independently from `os.walk` and `lstat`, never from the module.
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
from tests.support.snapshots import assert_json_snapshot

MIB = 1024 * 1024
DF_ARGV = ("df", "-k", "/System/Volumes/Data")
DF_HEADER = (
    "Filesystem    1024-blocks      Used Available Capacity iused ifree %iused"
    "  Mounted on\n"
)


def df_output(used_kb: int, total_kb: int = 971350180) -> str:
    available = total_kb - used_kb
    return (
        DF_HEADER + f"/dev/disk3s5 {total_kb} {used_kb} {available} 33% 1 2 0%"
        "   /System/Volumes/Data\n"
    )


@dataclass
class FakeDf:
    """Answers `df -k /System/Volumes/Data` and records every argv."""

    answer: str | Exception = field(default_factory=lambda: df_output(10**6))
    returncode: int = 0
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, argv: Sequence[str]) -> runner.RunResult:
        self.calls.append(tuple(argv))
        if isinstance(self.answer, Exception):
            raise self.answer
        return runner.RunResult(
            argv=tuple(argv),
            executable="/bin/df",
            returncode=self.returncode,
            stdout=self.answer,
            stderr="",
            stdout_bytes=len(self.answer.encode()),
        )


@dataclass
class World:
    data: Path
    home: Path
    df: FakeDf
    lstat: Callable[[str], Any] = fsread.lstat

    def environment(self) -> DiskMapEnvironment:
        volume = DataVolume(str(self.data), os.lstat(self.data).st_dev)
        return DiskMapEnvironment(volume, str(self.home), self.df, self.lstat)


@pytest.fixture
def world(tmp_path: Path) -> World:
    data = tmp_path.resolve() / "data"
    home = data / "Users" / "example"
    home.mkdir(parents=True)
    return World(data, home, FakeDf())


def make_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
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


def populate(world: World) -> tuple[Path, Path]:
    docs = world.home / "Documents"
    make_file(docs / "big" / "a.bin", 300_000)
    make_file(docs / "big" / "nested" / "b.bin", 100_000)
    make_file(docs / "small" / "c.bin", 10_000)
    make_file(docs / "loose.txt", 5_000)
    make_file(docs / "large" / "movie.mov", MIB + MIB // 2)
    music = world.home / "Music"
    make_file(music / "album" / "track.m4a", 200_000)
    return docs, music


# Happy path and accounting matrix


def test_happy_path_snapshot(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    docs, music = populate(world)
    world.df.answer = df_output(5000)
    result, payload = run_map(
        monkeypatch, world, [docs, music], "--large-file-min", "1"
    )

    assert result.exit_code == 0, result.stderr
    assert_json_snapshot(payload, "disk-map", roots=[world.data])


def test_root_and_first_level_totals_match_independent_lstat(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, music = populate(world)
    _, payload = run_map(monkeypatch, world, [docs, music])

    roots = findings_of(payload, "root_total")
    assert roots[str(docs)]["allocated_bytes"] == expected_allocated(docs)
    assert roots[str(docs)]["logical_bytes"] == expected_logical(docs)
    assert roots[str(docs)]["details"]["counted_allocated_bytes"] == (
        expected_allocated(docs)
    )
    assert roots[str(docs)]["details"]["overlap"] is None
    assert roots[str(docs)]["details"]["given"] == str(docs)
    first = findings_of(payload, "first_level")
    for name in ("big", "small", "large"):
        assert first[str(docs / name)]["allocated_bytes"] == expected_allocated(
            docs / name
        )
        assert first[str(docs / name)]["details"] == {"root": str(docs)}
    assert str(docs / "loose.txt") not in first
    measured = expected_allocated(docs, music)
    assert payload["data"]["summary"] == {
        "root_count": 2,
        "finding_count": len(payload["data"]["findings"]),
        "measured_allocated_bytes": measured,
    }


def test_nested_root_is_displayed_but_counted_once(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    inner = docs / "big"
    _, payload = run_map(monkeypatch, world, [inner, docs])

    roots = findings_of(payload, "root_total")
    outer_total, inner_total = roots[str(docs)], roots[str(inner)]
    assert inner_total["allocated_bytes"] == expected_allocated(inner)
    assert inner_total["logical_bytes"] == expected_logical(inner)
    assert inner_total["details"]["counted_allocated_bytes"] == 0
    assert inner_total["details"]["overlap"] == "inside_scan_root"
    assert "inside_other_scope" in inner_total["caveats"]
    assert outer_total["details"]["counted_allocated_bytes"] == (
        expected_allocated(docs)
    )
    first = findings_of(payload, "first_level")
    assert first[str(inner / "nested")]["details"] == {"root": str(inner)}
    assert first[str(inner / "nested")]["allocated_bytes"] == expected_allocated(
        inner / "nested"
    )
    reconciliation = payload["data"]["reconciliation"]
    assert reconciliation["measured_allocated_bytes"] == expected_allocated(docs)
    assert [c["finding_id"] for c in reconciliation["contributions"]] == [
        outer_total["id"],
        inner_total["id"],
    ]


def test_duplicate_and_aliased_roots_are_merged(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    alias = world.data / "alias-to-docs"
    alias.symlink_to(docs)
    _, payload = run_map(monkeypatch, world, [docs, alias, docs])

    roots = findings_of(payload, "root_total")
    assert list(roots) == [str(docs)]
    assert roots[str(docs)]["details"]["given"] == str(docs)
    assert payload["meta"]["scope"]["roots"] == [
        {"path": str(docs), "given": str(docs), "st_dev": os.lstat(docs).st_dev}
    ]
    assert payload["data"]["summary"]["root_count"] == 1
    assert payload["data"]["reconciliation"]["measured_allocated_bytes"] == (
        expected_allocated(docs)
    )


def test_hard_link_across_disjoint_roots_is_counted_once(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, music = populate(world)
    os.link(docs / "big" / "a.bin", music / "album" / "a-link.bin")
    _, payload = run_map(monkeypatch, world, [docs, music])

    roots = findings_of(payload, "root_total")
    assert roots[str(music)]["allocated_bytes"] == expected_allocated(music)
    linked = os.lstat(docs / "big" / "a.bin").st_blocks * 512
    assert roots[str(music)]["details"]["counted_allocated_bytes"] == (
        expected_allocated(music) - linked
    )
    for target in (docs, music):
        assert "hard_links_merged" in roots[str(target)]["caveats"]
    assert payload["data"]["summary"]["measured_allocated_bytes"] == (
        expected_allocated(docs, music)
    )


def test_hard_link_across_first_level_folders(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    os.link(docs / "big" / "a.bin", docs / "small" / "a-link.bin")
    _, payload = run_map(monkeypatch, world, [docs])

    first = findings_of(payload, "first_level")
    for name in ("big", "small"):
        assert first[str(docs / name)]["allocated_bytes"] == expected_allocated(
            docs / name
        )
        assert first[str(docs / name)]["caveats"] == ["hard_links_merged"]
    assert first[str(docs / "large")]["caveats"] == []
    root = findings_of(payload, "root_total")[str(docs)]
    assert root["allocated_bytes"] == expected_allocated(docs)
    assert root["caveats"] == ["apfs_clone_or_shared_extent", "hard_links_merged"]


def test_permission_failure_is_a_coverage_gap(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    locked = docs / "small"
    expected = (
        expected_allocated(docs)
        - expected_allocated(locked)
        + (os.lstat(locked).st_blocks * 512)
    )
    locked.chmod(0)
    try:
        result, payload = run_map(monkeypatch, world, [docs])
    finally:
        locked.chmod(0o755)

    assert result.exit_code == 0
    assert payload["meta"]["status"] == "partial"
    assert payload["meta"]["incomplete_coverage"] == [
        {
            "path": str(locked),
            "reason": "permission_denied",
            "errno": "EACCES",
            "operation": "scandir",
        }
    ]
    root = findings_of(payload, "root_total")[str(docs)]
    assert root["allocated_bytes"] == expected


def test_descent_never_crosses_a_device_change(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    mounted = docs / "big"
    real = fsread._entry_lstat

    def fake(entry: os.DirEntry[str]) -> Any:
        info = real(entry)
        return OtherDevice(info) if entry.path == str(mounted) else info

    monkeypatch.setattr(fsread, "_entry_lstat", fake)
    _, payload = run_map(monkeypatch, world, [docs])

    assert payload["meta"]["scope"]["skipped_mounts"] == [str(mounted)]
    root = findings_of(payload, "root_total")[str(docs)]
    assert root["allocated_bytes"] == expected_allocated(docs) - expected_allocated(
        mounted
    )
    assert str(mounted) not in findings_of(payload, "first_level")
    assert payload["meta"]["status"] == "complete"


class OtherDevice:
    """An lstat result whose st_dev differs from its real device."""

    def __init__(self, info: Any) -> None:
        self._info = info

    def __getattr__(self, name: str) -> Any:
        if name == "st_dev":
            return self._info.st_dev + 1
        return getattr(self._info, name)


# Roots and the data volume


def test_root_on_another_volume_exits_3(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, music = populate(world)

    def lstat(path: str) -> Any:
        info = os.lstat(path)
        return OtherDevice(info) if path == str(music) else info

    world.lstat = lstat
    result, _ = run_map(monkeypatch, world, [docs, music])

    assert result.exit_code == 3
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["code"] == "validation_error"
    assert "data volume" in error["reason"]
    assert world.df.calls == []


def test_firmlinked_root_maps_to_its_data_volume_form(tmp_path: Path) -> None:
    data = tmp_path.resolve()
    (data / "Users" / "example").mkdir(parents=True)
    real = data / "Users" / "example"
    volume = DataVolume(str(data), os.lstat(data).st_dev)

    def lstat(path: str) -> Any:
        return os.lstat(real if path == "/Users/example" else path)

    root = disk_map.canonical_root("/Users/example", volume, lstat, validate=Path)

    assert root.path == str(real)
    assert root.given == "/Users/example"
    assert root.st_dev == volume.st_dev


def test_root_without_a_data_volume_form_exits_3(tmp_path: Path) -> None:
    data = tmp_path.resolve() / "data"
    data.mkdir()
    outside = tmp_path.resolve() / "outside"
    outside.mkdir()
    volume = DataVolume(str(data), os.lstat(data).st_dev)

    with pytest.raises(disk_map.ValidationError) as caught:
        disk_map.canonical_root(str(outside), volume, fsread.lstat)

    assert caught.value.exit_code == 3


@pytest.mark.skipif(
    not os.path.isdir("/System/Volumes/Data/Users"), reason="needs macOS APFS"
)
def test_real_firmlink_users_maps_to_the_data_volume() -> None:
    volume = disk_map.default_environment().volume
    root = disk_map.canonical_root("/Users", volume, fsread.lstat)

    assert root.path == "/System/Volumes/Data/Users"
    with pytest.raises(disk_map.ValidationError):
        disk_map.canonical_root("/System", volume, fsread.lstat)


def test_missing_root_exits_3(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    result, _ = run_map(monkeypatch, world, [world.home / "missing"])

    assert result.exit_code == 3
    assert json.loads(result.stderr)["code"] == "validation_error"


def test_missing_data_volume_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(disk_map, "DATA_VOLUME_MOUNT", "/nonexistent-data-volume")
    with pytest.raises(disk_map.ValidationError):
        disk_map.default_environment()


def test_default_environment_reads_home_and_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(disk_map, "DATA_VOLUME_MOUNT", str(tmp_path))
    monkeypatch.setenv("HOME", "/Users/someone")
    env = disk_map.default_environment()

    assert env.volume == DataVolume(str(tmp_path), os.lstat(tmp_path).st_dev)
    assert env.home == "/Users/someone"


def test_default_runner_uses_the_allowlisted_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Sequence[str]] = []

    def fake_run(argv: Sequence[str]) -> str:
        seen.append(argv)
        return "result"

    monkeypatch.setattr(runner, "run", fake_run)
    assert disk_map.default_df_runner(DF_ARGV) == "result"
    assert seen == [DF_ARGV]


# Reconciliation


def test_reconciliation_reports_a_signed_delta(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    world.df.answer = df_output(used_kb=50_000, total_kb=100_000)
    _, payload = run_map(monkeypatch, world, [docs])

    measured = expected_allocated(docs)
    reconciliation = payload["data"]["reconciliation"]
    assert world.df.calls == [DF_ARGV]
    assert reconciliation["df_command"] == "df -k /System/Volumes/Data"
    assert reconciliation["df_used_bytes"] == 50_000 * 1024
    assert reconciliation["measured_allocated_bytes"] == measured
    assert reconciliation["delta_bytes"] == 50_000 * 1024 - measured
    assert reconciliation["overcount"] is False
    assert payload["data"]["system"] == {
        "df_data_volume": {
            "mount": "/System/Volumes/Data",
            "total_bytes": 100_000 * 1024,
            "used_bytes": 50_000 * 1024,
            "available_bytes": 50_000 * 1024,
        }
    }
    assert payload["meta"]["cost"]["subprocess_calls"] == 1


def test_measured_above_df_is_a_negative_overcount(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    world.df.answer = df_output(used_kb=1)
    _, payload = run_map(monkeypatch, world, [docs])

    reconciliation = payload["data"]["reconciliation"]
    assert reconciliation["delta_bytes"] == 1024 - expected_allocated(docs)
    assert reconciliation["delta_bytes"] < 0
    assert reconciliation["overcount"] is True


@pytest.mark.parametrize(
    "answer",
    [
        runner.ExecutableNotFoundError(DF_ARGV, "df is not installed"),
        runner.CommandTimeoutError(DF_ARGV, "df timed out after 60 s", 60),
        "garbage output\n",
        "",
    ],
)
def test_df_failure_exits_4(
    monkeypatch: pytest.MonkeyPatch, world: World, answer: str | Exception
) -> None:
    docs, _ = populate(world)
    world.df.answer = answer
    result, _ = run_map(monkeypatch, world, [docs])

    assert result.exit_code == 4
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["code"] == "source_unavailable"
    assert error["help"] == "byte-census disk map --help"


def test_df_nonzero_exit_exits_4(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    docs, _ = populate(world)
    world.df.returncode = 1
    result, _ = run_map(monkeypatch, world, [docs])

    assert result.exit_code == 4
    assert "exited with status 1" in json.loads(result.stderr)["reason"]


def test_parse_df_reads_the_numeric_columns() -> None:
    usage = disk_map.parse_df(df_output(used_kb=7, total_kb=10))

    assert (usage.total_bytes, usage.used_bytes, usage.available_bytes) == (
        10 * 1024,
        7 * 1024,
        3 * 1024,
    )


# Selection, ordering, large files


def test_top_truncates_display_after_complete_totals(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, _ = populate(world)
    _, full = run_map(monkeypatch, world, [docs])
    result, cut = run_map(monkeypatch, world, [docs], "--top", "1")

    assert result.exit_code == 0
    first = findings_of(cut, "first_level")
    assert list(first) == [str(docs / "large")]
    assert cut["meta"]["scope"]["options"] == {"top": 1, "large_file_min_mb": 500}
    for key in ("measured_allocated_bytes",):
        assert cut["data"]["summary"][key] == full["data"]["summary"][key]
    assert findings_of(cut, "root_total") == findings_of(full, "root_total")


def test_default_top_is_thirty(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    root = world.home / "many"
    for index in range(35):
        make_file(root / f"d{index:02d}" / "f.bin", 1000 + index)
    _, payload = run_map(monkeypatch, world, [root])

    assert len(findings_of(payload, "first_level")) == 30
    assert payload["meta"]["scope"]["options"]["top"] == 30


def test_large_files_rank_by_logical_bytes(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = world.home / "files"
    make_file(root / "a" / "dense.bin", 2 * MIB)
    sparse = root / "b" / "sparse.img"
    sparse.parent.mkdir(parents=True)
    with sparse.open("wb") as handle:
        handle.truncate(3 * MIB)
    make_file(root / "c" / "exact.bin", MIB)
    _, payload = run_map(monkeypatch, world, [root], "--large-file-min", "1")

    large = [f for f in payload["data"]["findings"] if f["kind"] == "large_file"]
    assert [f["target"] for f in large] == [str(sparse), str(root / "a/dense.bin")]
    assert large[0]["logical_bytes"] == 3 * MIB
    assert large[0]["allocated_bytes"] == os.lstat(sparse).st_blocks * 512
    assert large[0]["caveats"] == ["sparse_file"]
    assert large[0]["details"] == {"root": str(root)}


def test_large_files_are_capped_per_root(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    root = world.home / "files"
    for index in range(90):
        make_file(root / f"f{index:02d}.bin", 10 + index)
    _, payload = run_map(monkeypatch, world, [root], "--large-file-min", "0")

    large = findings_of(payload, "large_file")
    assert len(large) == 20
    assert str(root / "f00.bin") not in large


def test_findings_order_is_kind_then_size_then_target(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    docs, music = populate(world)
    _, payload = run_map(monkeypatch, world, [music, docs], "--large-file-min", "1")

    kinds = [f["kind"] for f in payload["data"]["findings"]]
    assert kinds == sorted(kinds, key=["root_total", "first_level", "large_file"].index)
    first = [f for f in payload["data"]["findings"] if f["kind"] == "first_level"]
    keys = [(-f["allocated_bytes"], f["target"]) for f in first]
    assert keys == sorted(keys)


def test_output_is_deterministic(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    docs, music = populate(world)
    first, _ = run_map(monkeypatch, world, [docs, music])
    second, _ = run_map(monkeypatch, world, [music, docs])
    a, b = json.loads(first.stdout), json.loads(second.stdout)
    for payload in (a, b):
        payload["meta"]["captured_at"] = payload["meta"]["cost"]["elapsed_s"] = None

    assert a == b


# Observational output: no suggestions, see_check


def test_no_suggestions_and_see_check_precedence(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    library = world.home / "Library"
    make_file(library / "Caches" / "app" / "c.bin", 1000)
    docker = library / "Containers" / "com.docker.docker"
    make_file(docker / "Data" / "Docker.raw", 2 * MIB)
    project = world.home / "project"
    make_file(project / "node_modules" / "m.js", 1000)
    make_file(project / "rust" / "Cargo.toml", 10)
    make_file(project / "rust" / "target" / "t.o", 1000)
    make_file(project / "plain" / "target" / "t.o", 1000)
    make_file(world.home / "Downloads" / "big.iso", 2 * MIB)
    roots = [library, project, world.home / "Downloads", world.home]
    _, payload = run_map(monkeypatch, world, roots, "--large-file-min", "1")

    assert payload["data"]["suggestions"] == []
    assert all(f["suggestion_ids"] == [] for f in payload["data"]["findings"])
    roots_found = findings_of(payload, "root_total")
    assert roots_found[str(world.home / "Downloads")]["see_check"] == (
        "duplicates scan"
    )
    assert roots_found[str(library)]["see_check"] is None
    first = findings_of(payload, "first_level")
    assert first[str(library / "Caches")]["see_check"] == "caches scan"
    assert first[str(project / "node_modules")]["see_check"] == "artifacts scan"
    assert first[str(project / "rust")]["see_check"] is None
    assert first[str(world.home / "Downloads")]["see_check"] == "duplicates scan"
    assert first[str(project / "plain")]["see_check"] is None
    large = findings_of(payload, "large_file")
    assert large[str(docker / "Data" / "Docker.raw")]["see_check"] == "docker scan"
    assert large[str(world.home / "Downloads" / "big.iso")]["see_check"] == (
        "duplicates scan"
    )


def test_see_check_rules() -> None:
    home = "/System/Volumes/Data/Users/x"
    rules = disk_map.SeeCheckRules.for_home("/Users/x", "/System/Volumes/Data")

    def check(target: str, kind: str = "first_level") -> str | None:
        return rules.see_check(target, kind, exists=lambda _: False)

    assert check(home + "/Library/Containers/com.docker.docker/x") == "docker scan"
    assert check(home + "/Library/Caches") == "caches scan"
    assert check("/Users/x/Library/Caches/a") == "caches scan"
    assert check(home + "/a/.venv/lib") == "artifacts scan"
    assert check(home + "/a/venv") == "artifacts scan"
    assert check(home + "/a/target") is None
    assert (
        rules.see_check(home + "/a/target", "first_level", exists=lambda _: True)
        == "artifacts scan"
    )
    assert check(home + "/Library/Caches/big.bin", "large_file") == "caches scan"
    assert check(home + "/big.bin", "large_file") == "duplicates scan"
    assert check(home + "/Downloads") == "duplicates scan"
    assert check(home + "/Downloads/sub") is None
    assert check(home + "/Documents") is None


# CLI surface


def test_scan_root_is_required() -> None:
    result = CliRunner().invoke(main, ["disk", "map"])

    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "usage_error"


@pytest.mark.parametrize(
    "args", [["--top", "0"], ["--top", "x"], ["--large-file-min", "-1"]]
)
def test_invalid_options_are_usage_errors(args: list[str], world: World) -> None:
    result = CliRunner().invoke(
        main, ["disk", "map", "--scan-root", str(world.home), *args]
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert json.loads(result.stderr)["code"] == "usage_error"


def test_missing_option_value_names_the_subcommand() -> None:
    result = CliRunner().invoke(main, ["disk", "map", "--scan-root"])

    assert result.exit_code == 2
    assert json.loads(result.stderr)["help"] == "byte-census disk map --help"


def test_unexpected_failure_exits_1(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    def boom(*_: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(disk_map, "disk_map", boom)
    result, _ = run_map(monkeypatch, world, [world.home])

    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "internal_error"


def test_table_format(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    docs, _ = populate(world)
    install(monkeypatch, world)
    result = CliRunner().invoke(
        main, ["disk", "map", "--scan-root", str(docs), "--format", "table"]
    )

    assert result.exit_code == 0
    assert "big" in result.stdout
    assert "\x1b[" not in result.stdout


@pytest.mark.parametrize("flag", ["-h", "--help"])
@pytest.mark.parametrize("path", [["disk", "map"], ["disk"]])
def test_help_has_usage_and_example(path: list[str], flag: str) -> None:
    result = CliRunner().invoke(main, [*path, flag])

    assert result.exit_code == 0
    assert result.stdout.startswith("Usage:")
    assert "Example:" in result.stdout
