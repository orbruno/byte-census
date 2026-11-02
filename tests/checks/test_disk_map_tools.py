"""Regression tests for tool-cache associations and Docker cost in disk map
(review of the WI-DISK-MAP-CATEGORIES round)."""

from pathlib import Path

import pytest

from tests.support.disk_map_world import (
    BREW_ARGV,
    DOCKER_ARGV,
    UV_ARGV,
    World,
    findings_of,
    make_file,
    new_world,
    run_map,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    world = new_world(tmp_path)
    make_file(world.home / "Documents" / "f.bin", 1000)
    return world


def test_unreadable_npmrc_marks_the_fallback_location_uncertain(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    npmrc = make_file(world.home / ".npmrc", 20)
    npm = world.home / ".npm"
    make_file(npm / "_cacache" / "index", 5_000)
    npmrc.chmod(0)
    try:
        _, payload = run_map(monkeypatch, world, [world.home / "Documents"])
    finally:
        npmrc.chmod(0o644)

    found = findings_of(payload, "tool_cache")[str(npm)]
    assert str(npmrc) in found["details"]["location_uncertain"]
    gaps = {e["path"]: e for e in payload["meta"]["incomplete_coverage"]}
    assert gaps[str(npmrc)]["operation"] == "read"
    assert payload["meta"]["status"] == "partial"


def test_readable_location_is_not_uncertain(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    npm = world.home / ".npm"
    make_file(npm / "index", 5_000)
    _, payload = run_map(monkeypatch, world, [world.home / "Documents"])

    assert (
        "location_uncertain"
        not in findings_of(payload, "tool_cache")[str(npm)]["details"]
    )


def test_tools_sharing_a_location_keep_their_association(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    shared = world.home / ".cache" / "shared"
    make_file(shared / "blob", 4_000)
    world.runner.answers[UV_ARGV] = str(shared) + "\n"
    world.runner.answers[BREW_ARGV] = str(shared) + "\n"
    _, payload = run_map(monkeypatch, world, [world.home / "Documents"])

    caches = findings_of(payload, "tool_cache")
    assert list(caches) == [str(shared)]
    details = caches[str(shared)]["details"]
    assert details["tool"] == "uv"
    assert details["other_tools"] == [
        {"tool": "brew", "location_source": "brew --cache"}
    ]
    assert payload["data"]["suggestions"] == []


def test_malformed_docker_output_keeps_its_stdout_cost(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    garbage = "this is not json at all\n"
    world.runner.answers[DOCKER_ARGV] = garbage
    _, payload = run_map(monkeypatch, world, [world.home / "Documents"])

    answered = [
        world.runner.answers[call]
        for call in world.runner.calls
        if isinstance(world.runner.answers.get(call), str)
    ]
    expected = sum(len(text.encode()) for text in answered)
    assert DOCKER_ARGV in world.runner.calls
    assert payload["meta"]["cost"]["subprocess_stdout_bytes"] == expected
    assert expected >= len(garbage)


def test_shared_location_keeps_the_uncertainty_of_every_tool(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    npmrc = make_file(world.home / ".npmrc", 20)
    npm = world.home / ".npm"
    make_file(npm / "_cacache" / "index", 5_000)
    world.runner.answers[UV_ARGV] = str(npm) + "\n"
    npmrc.chmod(0)
    try:
        _, payload = run_map(monkeypatch, world, [world.home / "Documents"])
    finally:
        npmrc.chmod(0o644)

    caches = findings_of(payload, "tool_cache")
    assert list(caches) == [str(npm)]
    details = caches[str(npm)]["details"]
    assert details["tool"] == "uv"
    assert [other["tool"] for other in details["other_tools"]] == ["npm"]
    assert str(npmrc) in details["location_uncertain"]
