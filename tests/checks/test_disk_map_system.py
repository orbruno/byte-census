"""Tests for disk map system context (WI-DISK-MAP-CATEGORIES AC-03).

Every command is answered by the fake runner; df, diskutil, tmutil, and
docker never run.
"""

from pathlib import Path
from typing import Any

import pytest

from byte_census import runner
from byte_census.checks.disk_map_system import (
    Unusable,
    count_snapshots,
    docker_reported_size,
    parse_diskutil,
)
from tests.support.disk_map_world import (
    DISKUTIL_ARGV,
    DOCKER_ARGV,
    DOCKER_TEXT,
    SYSTEM_DF_ARGV,
    TMUTIL_ARGV,
    World,
    make_file,
    new_world,
    run_map,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    world = new_world(tmp_path)
    make_file(world.home / "Documents" / "f.bin", 1000)
    return world


def system_of(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> tuple[dict[str, Any], dict[str, Any]]:
    result, payload = run_map(monkeypatch, world, [world.home / "Documents"])
    assert result.exit_code == 0, result.stderr
    return payload["data"]["system"], payload["meta"]


def test_system_context_matches_the_contract_shape(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    world.runner.answers[DOCKER_ARGV] = DOCKER_TEXT
    system, meta = system_of(monkeypatch, world)

    assert list(system) == [
        "df_data_volume",
        "df_system_volume",
        "diskutil",
        "local_snapshot_count",
        "docker_informational",
    ]
    assert system["df_system_volume"] == {"mount": "/", "used_bytes": 11977488 * 1024}
    assert system["diskutil"] == {
        "volume_name": "Macintosh HD",
        "file_system_personality": "APFS",
        "container_total_space": "994.7 GB (994662584320 Bytes)",
        "container_free_space": "350.1 GB (350108332032 Bytes)",
    }
    assert system["local_snapshot_count"] == 2
    assert system["docker_informational"] == {
        "available": True,
        "docker_reported_size_bytes": 11784600000,
        "summed_into_host_totals": False,
        "see_check": "docker scan",
    }
    assert meta["status"] == "complete"


def test_docker_is_never_added_to_host_totals(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    _, without = run_map(monkeypatch, world, [world.home / "Documents"])
    world.runner.answers[DOCKER_ARGV] = DOCKER_TEXT
    _, with_docker = run_map(monkeypatch, world, [world.home / "Documents"])

    key = "measured_allocated_bytes"
    assert with_docker["data"]["summary"][key] == without["data"]["summary"][key]
    assert without["data"]["system"]["docker_informational"]["available"] is False


def test_every_call_is_an_allowlisted_argv(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    system_of(monkeypatch, world)

    for argv in world.runner.calls:
        runner.match_template(argv)
    assert world.runner.calls[:5] == [
        ("df", "-k", "/System/Volumes/Data"),
        SYSTEM_DF_ARGV,
        DISKUTIL_ARGV,
        TMUTIL_ARGV,
        DOCKER_ARGV,
    ]


FAILURES = [
    (SYSTEM_DF_ARGV, (1, "", "df: /: error"), "df_system_volume", "failed", "df_system_volume"),
    (SYSTEM_DF_ARGV, "garbage\n", "df_system_volume", "failed", "df_system_volume"),
    (DISKUTIL_ARGV, runner.CommandTimeoutError(DISKUTIL_ARGV, "timed out", 60), "diskutil", "timed_out", "diskutil"),
    (DISKUTIL_ARGV, "nothing useful\n", "diskutil", "failed", "diskutil"),
    (TMUTIL_ARGV, (1, "", "tmutil: error"), "tmutil", "failed", "local_snapshot_count"),
    (DOCKER_ARGV, "not json\n", "docker", "failed", None),
    (DOCKER_ARGV, "", "docker", "failed", None),
]  # fmt: skip


@pytest.mark.parametrize(("argv", "answer", "source", "reason", "field"), FAILURES)
def test_failed_optional_sources_make_the_result_partial(
    monkeypatch: pytest.MonkeyPatch,
    world: World,
    argv: tuple[str, ...],
    answer: Any,
    source: str,
    reason: str,
    field: str | None,
) -> None:
    world.runner.answers[argv] = answer
    system, meta = system_of(monkeypatch, world)

    assert {"source": source, "reason": reason} == {
        k: v
        for entry in meta["unavailable_sources"]
        if entry["source"] == source
        for k, v in entry.items()
        if k != "detail"
    }
    assert meta["status"] == "partial"
    if field is not None:
        assert system[field] is None
    else:
        assert system["docker_informational"]["available"] is False


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ((1, "", "Cannot connect to the Docker daemon at unix:///x"), "not_running"),
        (
            runner.ExecutableNotFoundError(DOCKER_ARGV, "docker missing"),
            "not_installed",
        ),
    ],
)
def test_docker_down_or_missing_is_not_partial(
    monkeypatch: pytest.MonkeyPatch, world: World, answer: Any, reason: str
) -> None:
    world.runner.answers[DOCKER_ARGV] = answer
    system, meta = system_of(monkeypatch, world)

    entry = next(s for s in meta["unavailable_sources"] if s["source"] == "docker")
    assert entry["reason"] == reason
    assert system["docker_informational"]["docker_reported_size_bytes"] is None
    assert meta["status"] == "complete"


def test_rejected_argv_is_an_internal_error(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    world.runner.answers[TMUTIL_ARGV] = runner.RejectedArgvError(TMUTIL_ARGV, "no")
    result, _ = run_map(monkeypatch, world, [world.home / "Documents"])

    assert result.exit_code == 1


def test_parsers() -> None:
    assert count_snapshots("Snapshots for disk /:\n") == 0
    assert parse_diskutil("   Volume Name: X\n") == {
        "volume_name": "X",
        "file_system_personality": None,
        "container_total_space": None,
        "container_free_space": None,
    }
    assert docker_reported_size('{"Size":"1kB"}\n{"Size":"0B"}\n') == 1000
    with pytest.raises(Unusable):
        docker_reported_size('{"Size":"lots"}\n')
    with pytest.raises(Unusable):
        docker_reported_size("[1]\n")
