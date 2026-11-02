"""Tests for `byte-census caches scan` (WI-CACHES AC-01 to AC-04).

Every tree is built in tmp_path. The home directory and the Caches root are
injected; tools run through a fake runner and npm is never executed.
"""

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner, Result

from byte_census import runner
from byte_census.checks import caches
from byte_census.checks.caches import CachesEnvironment
from byte_census.cli import main
from tests.support.snapshots import allocated_bytes_of, assert_json_snapshot

BLOCK = 4096


def make_file(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def tree_allocated(path: Path) -> int:
    total = allocated_bytes_of(path)
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            total += allocated_bytes_of(Path(dirpath) / name)
    return total


def run_result(argv: Sequence[str], stdout: str, code: int = 0) -> runner.RunResult:
    return runner.RunResult(
        argv=tuple(argv),
        executable="/fake/" + argv[0],
        returncode=code,
        stdout=stdout,
        stderr="",
        stdout_bytes=len(stdout.encode()),
    )


@dataclass
class FakeTools:
    """Answers the two allowlisted tool commands and records every argv."""

    uv: str | Exception | None = None
    brew: str | Exception | None = None
    fixed_stdout_bytes: int | None = None
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, argv: Sequence[str]) -> runner.RunResult:
        self.calls.append(tuple(argv))
        answer = {"uv": self.uv, "brew": self.brew}[argv[0]]
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise runner.ExecutableNotFoundError(argv, f"{argv[0]} is not installed")
        result = run_result(argv, answer + "\n")
        if self.fixed_stdout_bytes is None:
            return result
        return replace(result, stdout_bytes=self.fixed_stdout_bytes)


@dataclass(frozen=True)
class World:
    home: Path
    caches: Path
    tools: FakeTools
    environ: dict[str, str]

    def environment(self) -> CachesEnvironment:
        return CachesEnvironment(
            str(self.home), str(self.caches), self.environ, self.tools
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    home = tmp_path.resolve() / "home"
    root = home / "Library" / "Caches"
    root.mkdir(parents=True)
    environ = {"HOME": str(home)}
    return World(home, root, FakeTools(), environ)


def install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    monkeypatch.setattr(caches, "default_environment", world.environment)


def scan(
    monkeypatch: pytest.MonkeyPatch, world: World, *args: str
) -> tuple[Result, dict[str, Any]]:
    install(monkeypatch, world)
    result = CliRunner().invoke(main, ["caches", "scan", *args])
    payload = json.loads(result.stdout) if result.stdout else {}
    return result, payload


def populate(world: World) -> None:
    make_file(world.caches / "big" / "a.bin", 300_000)
    make_file(world.caches / "medium" / "sub" / "b.bin", 100_000)
    make_file(world.caches / "small" / "c.bin", 10_000)
    make_file(world.caches / "Homebrew" / "d.bin", 200_000)
    make_file(world.caches / "loose-file.txt", 50_000)
    uv_dir = world.home / ".cache" / "uv"
    make_file(uv_dir / "wheel.bin", 150_000)
    world.tools.uv = str(uv_dir)
    world.tools.brew = str(world.caches / "Homebrew")


def by_target(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["target"]: f for f in payload["data"]["findings"]}


def test_happy_path_snapshot(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    populate(world)
    world.tools.fixed_stdout_bytes = 40
    result, payload = scan(monkeypatch, world)

    assert result.exit_code == 0, result.stderr
    assert_json_snapshot(payload, "caches-scan", roots=[world.home])


def test_sizes_are_allocated_bytes_of_each_folder(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, payload = scan(monkeypatch, world)

    found = by_target(payload)
    big = found[str(world.caches / "big")]
    assert big["allocated_bytes"] == tree_allocated(world.caches / "big")
    assert big["logical_bytes"] == 300_000
    assert big["reclaimable_estimate_bytes"] == big["allocated_bytes"]
    assert big["caveats"] == ["apfs_clone_or_shared_extent"]
    assert found[str(world.caches / "medium")]["allocated_bytes"] == tree_allocated(
        world.caches / "medium"
    )


def test_totals_are_complete_before_truncating_to_top(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, full = scan(monkeypatch, world)
    result, cut = scan(monkeypatch, world, "--top", "2")

    assert result.exit_code == 0
    summary = cut["data"]["summary"]
    assert summary["top"] == 2
    assert summary["shown"] == 2
    assert summary["truncated"] is True
    assert len(cut["data"]["findings"]) == 2
    assert summary["cache_dir_count"] == full["data"]["summary"]["cache_dir_count"]
    assert (
        summary["total_allocated_bytes"]
        == full["data"]["summary"]["total_allocated_bytes"]
    )
    assert cut["meta"]["scope"]["options"] == {"top": 2}
    shown = [f["allocated_bytes"] for f in cut["data"]["findings"]]
    assert shown == sorted(shown, reverse=True)


def test_default_top_is_twenty(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    for index in range(25):
        make_file(world.caches / f"app-{index:02d}" / "f.bin", 1000)
    _, payload = scan(monkeypatch, world)

    summary = payload["data"]["summary"]
    assert (summary["top"], summary["shown"], summary["truncated"]) == (20, 20, True)
    assert summary["cache_dir_count"] == 25


def test_total_is_the_union_of_all_measured_trees(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, payload = scan(monkeypatch, world)

    findings = payload["data"]["findings"]
    assert payload["data"]["summary"]["total_allocated_bytes"] == sum(
        f["allocated_bytes"] for f in findings
    )
    assert payload["data"]["summary"]["tool_cache_count"] == 1


def test_loose_files_and_symlinks_are_not_cache_folders(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    outside = world.home / "elsewhere"
    make_file(outside / "z.bin", 900_000)
    (world.caches / "link-to-elsewhere").symlink_to(outside)
    _, payload = scan(monkeypatch, world)

    targets = set(by_target(payload))
    assert str(world.caches / "loose-file.txt") not in targets
    assert str(world.caches / "link-to-elsewhere") not in targets
    assert str(outside) not in targets


def test_brew_cache_inside_caches_is_reported_once_with_its_tool(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, payload = scan(monkeypatch, world)

    brew = [f for f in payload["data"]["findings"] if f["details"]["tool"] == "brew"]
    assert len(brew) == 1
    assert brew[0]["kind"] == "cache_dir"
    assert brew[0]["target"] == str(world.caches / "Homebrew")
    assert brew[0]["details"]["location_source"] == "brew --cache"
    assert brew[0]["classification"]["owner"] == "brew"
    roots = [r["path"] for r in payload["meta"]["scope"]["roots"]]
    assert str(world.caches / "Homebrew") not in roots


def finding_for(payload: dict[str, Any], target: Path) -> dict[str, Any]:
    return by_target(payload)[str(target)]


def suggestions_of(payload: dict[str, Any]) -> dict[str, list[str]]:
    return {s["id"]: s["finding_ids"] for s in payload["data"]["suggestions"]}


def test_tool_location_nested_inside_a_cache_folder_keeps_its_association(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, before = scan(monkeypatch, world)
    world.tools.brew = str(world.caches / "medium" / "sub")
    _, payload = scan(monkeypatch, world)

    medium = finding_for(payload, world.caches / "medium")
    assert medium["kind"] == "cache_dir"
    assert medium["suggestion_ids"] == ["brew-cleanup"]
    assert medium["details"]["tool"] == "brew"
    assert medium["details"]["tool_locations"] == [str(world.caches / "medium" / "sub")]
    assert suggestions_of(payload)["brew-cleanup"] == [medium["id"]]
    assert payload["data"]["summary"]["tool_cache_count"] == 1
    assert (
        payload["data"]["summary"]["total_allocated_bytes"]
        == before["data"]["summary"]["total_allocated_bytes"]
    )


def test_tool_cache_equal_to_the_caches_root_includes_root_level_files(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    world.tools.brew = str(world.caches)
    _, payload = scan(monkeypatch, world)

    root = finding_for(payload, world.caches)
    assert root["kind"] == "tool_cache"
    assert root["details"]["tool"] == "brew"
    assert root["logical_bytes"] >= 50_000 + 300_000 + 100_000 + 10_000 + 200_000
    expected = tree_allocated(world.caches) + allocated_bytes_of(world.caches)
    assert root["allocated_bytes"] == expected
    uv_dir = world.home / ".cache" / "uv"
    uv_bytes = tree_allocated(uv_dir) + allocated_bytes_of(uv_dir)
    assert payload["data"]["summary"]["total_allocated_bytes"] == expected + uv_bytes
    assert suggestions_of(payload)["brew-cleanup"] == [root["id"]]


def test_two_tools_at_one_location_each_keep_association_and_suggestion(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    uv_dir = world.home / ".cache" / "uv"
    world.environ["npm_config_cache"] = str(uv_dir)
    _, payload = scan(monkeypatch, world)

    found = finding_for(payload, uv_dir)
    assert found["kind"] == "tool_cache"
    assert found["suggestion_ids"] == ["npm-cache-verify", "uv-cache-prune"]
    assert found["details"]["tool"] == "uv"
    assert [t["tool"] for t in found["details"]["other_tools"]] == ["npm"]
    suggestions = suggestions_of(payload)
    assert suggestions["npm-cache-verify"] == [found["id"]]
    assert suggestions["uv-cache-prune"] == [found["id"]]
    assert payload["data"]["summary"]["tool_cache_count"] == 1


def test_tool_nested_inside_another_tool_cache_is_associated_not_remeasured(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    nested = world.home / ".cache" / "uv" / "npm-inside"
    make_file(nested / "n.bin", 1000)
    world.environ["npm_config_cache"] = str(nested)
    _, payload = scan(monkeypatch, world)

    assert str(nested) not in by_target(payload)
    uv = finding_for(payload, world.home / ".cache" / "uv")
    assert uv["suggestion_ids"] == ["npm-cache-verify", "uv-cache-prune"]
    assert payload["data"]["summary"]["tool_cache_count"] == 1


def test_tool_location_that_vanishes_is_a_coverage_gap_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    uv_dir = str(world.home / ".cache" / "uv")
    real = caches.fsread.lstat
    calls: list[str] = []

    def vanishing(path: Any) -> Any:
        if os.fspath(path) == uv_dir:
            calls.append(uv_dir)
            if len(calls) >= 3:
                raise FileNotFoundError(2, "gone", uv_dir)
        return real(path)

    monkeypatch.setattr(caches.fsread, "lstat", vanishing)
    result, payload = scan(monkeypatch, world)

    assert result.exit_code == 0, result.stderr
    assert uv_dir not in by_target(payload)
    gaps = [g for g in payload["meta"]["incomplete_coverage"] if g["path"] == uv_dir]
    assert gaps and gaps[0]["reason"] == "vanished"
    assert payload["meta"]["status"] == "partial"


@pytest.mark.parametrize("which", ["root", "data_volume", "home"])
def test_dangerous_tool_locations_are_rejected_and_not_walked(
    monkeypatch: pytest.MonkeyPatch, world: World, which: str
) -> None:
    populate(world)
    location = {
        "root": "/",
        "data_volume": "/System/Volumes/Data",
        "home": str(world.home),
    }[which]
    world.environ["npm_config_cache"] = location
    walked: list[str] = []
    real_walk = caches.fsread.walk
    real_measure = caches.measure_tree

    def spy(root: str, ledger: Any) -> Any:
        walked.append(root)
        if root == location:
            raise AssertionError(f"walked a forbidden location: {root}")
        return real_measure(root, ledger)

    monkeypatch.setattr(caches, "measure_tree", spy)
    result, payload = scan(monkeypatch, world)

    assert real_walk is not None
    assert result.exit_code == 0
    assert location not in walked
    npm = [u for u in payload["meta"]["unavailable_sources"] if u["source"] == "npm"]
    assert npm[0]["reason"] == "failed"
    assert "refus" in npm[0]["detail"]
    assert payload["meta"]["status"] == "partial"


def test_uv_cache_outside_caches_is_a_tool_cache(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, payload = scan(monkeypatch, world)

    uv = by_target(payload)[str(world.home / ".cache" / "uv")]
    assert uv["kind"] == "tool_cache"
    assert uv["details"] == {"tool": "uv", "location_source": "uv cache dir"}
    assert uv["classification"]["owner"] == "uv"
    given = {r["path"]: r["given"] for r in payload["meta"]["scope"]["roots"]}
    assert given[str(world.home / ".cache" / "uv")] == "uv cache dir"


def test_tools_are_asked_only_through_the_allowlisted_commands(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    make_file(world.home / ".npm" / "n.bin", 5000)
    scan(monkeypatch, world)

    assert world.tools.calls == [("uv", "cache", "dir"), ("brew", "--cache")]
    for argv in world.tools.calls:
        assert runner.match_template(argv) is not None


def test_npm_location_comes_from_configuration_and_is_measured(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    npm = make_file(world.home / "custom-npm" / "n.bin", 70_000).parent
    (world.home / ".npmrc").write_text(f"cache={npm}\n")
    _, payload = scan(monkeypatch, world)

    found = by_target(payload)[str(npm)]
    assert found["kind"] == "tool_cache"
    assert found["details"]["tool"] == "npm"
    assert found["details"]["location_source"] == f"npmrc:{world.home / '.npmrc'}"
    assert not [
        u for u in payload["meta"]["unavailable_sources"] if u["source"] == "npm"
    ]


def test_missing_tools_are_unavailable_not_errors(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    make_file(world.caches / "app" / "f.bin", 1000)
    result, payload = scan(monkeypatch, world)

    assert result.exit_code == 0
    assert result.stderr == ""
    sources = {u["source"]: u for u in payload["meta"]["unavailable_sources"]}
    assert set(sources) == {"uv", "brew", "npm"}
    assert {u["reason"] for u in sources.values()} == {"not_installed"}
    assert "was not found on PATH" in sources["uv"]["detail"]
    assert str(world.home / ".npm") in sources["npm"]["detail"]
    assert "default" in sources["npm"]["detail"]
    assert payload["meta"]["status"] == "complete"
    assert payload["data"]["suggestions"] == []


def test_tool_location_that_does_not_exist_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    world.tools.uv = str(world.home / "gone")
    _, payload = scan(monkeypatch, world)

    uv = [u for u in payload["meta"]["unavailable_sources"] if u["source"] == "uv"]
    assert uv[0]["reason"] == "not_installed"
    assert "does not exist" in uv[0]["detail"]


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (
            runner.CommandTimeoutError(("uv",), "uv timed out after 60 s", 60),
            "timed_out",
        ),
        (runner.CommandLaunchError(("uv",), "uv could not start"), "failed"),
        ("relative/path", "failed"),
        ("", "failed"),
        ("/one\n/two", "failed"),
    ],
)
def test_tool_failures_make_the_result_partial(
    monkeypatch: pytest.MonkeyPatch,
    world: World,
    answer: Any,
    reason: str,
) -> None:
    world.tools.uv = answer
    result, payload = scan(monkeypatch, world)

    assert result.exit_code == 0
    uv = [u for u in payload["meta"]["unavailable_sources"] if u["source"] == "uv"]
    assert uv[0]["reason"] == reason
    assert payload["meta"]["status"] == "partial"


def test_nonzero_exit_is_reported_as_failed(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    def failing(argv: Sequence[str]) -> runner.RunResult:
        return run_result(argv, "", code=3)

    install(monkeypatch, world)
    monkeypatch.setattr(
        caches,
        "default_environment",
        lambda: CachesEnvironment(
            str(world.home), str(world.caches), world.environ, failing
        ),
    )
    result = CliRunner().invoke(main, ["caches", "scan"])
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    reasons = {u["source"]: u["reason"] for u in payload["meta"]["unavailable_sources"]}
    assert reasons["uv"] == "failed"
    assert (
        "exited with status 3" in payload["meta"]["unavailable_sources"][-1]["detail"]
    )
    assert payload["meta"]["status"] == "partial"


def test_tool_caches_carry_low_risk_catalog_suggestions(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    npm = make_file(world.home / ".npm" / "n.bin", 5000).parent
    _, payload = scan(monkeypatch, world)

    suggestions = {s["id"]: s for s in payload["data"]["suggestions"]}
    assert {sid: s["command"] for sid, s in suggestions.items()} == {
        "brew-cleanup": "brew cleanup",
        "npm-cache-verify": "npm cache verify",
        "uv-cache-prune": "uv cache prune",
    }
    assert {s["risk"] for s in suggestions.values()} == {"low"}
    assert all(s["requires_owner_authorization"] for s in suggestions.values())
    found = by_target(payload)
    assert found[str(npm)]["suggestion_ids"] == ["npm-cache-verify"]
    assert suggestions["npm-cache-verify"]["finding_ids"] == [found[str(npm)]["id"]]
    plain = found[str(world.caches / "big")]
    assert plain["suggestion_ids"] == []


def test_suggestion_is_omitted_when_its_finding_is_cut_by_top(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, payload = scan(monkeypatch, world, "--top", "1")

    assert [f["details"]["tool"] for f in payload["data"]["findings"]] == [None]
    assert payload["data"]["suggestions"] == []


def test_hard_link_between_folders_is_counted_once_in_the_total(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    original = make_file(world.caches / "one" / "shared.bin", 200_000)
    (world.caches / "two").mkdir()
    os.link(original, world.caches / "two" / "alias.bin")
    _, payload = scan(monkeypatch, world)

    found = by_target(payload)
    one, two = found[str(world.caches / "one")], found[str(world.caches / "two")]
    assert one["allocated_bytes"] == two["allocated_bytes"]
    assert payload["data"]["summary"]["total_allocated_bytes"] == (
        one["allocated_bytes"] + two["allocated_bytes"] - allocated_bytes_of(original)
    )
    both = ["apfs_clone_or_shared_extent", "hard_links_merged"]
    assert two["caveats"] == both
    assert one["caveats"] == both


def test_unreadable_folder_is_a_coverage_gap_not_a_failure(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    make_file(world.caches / "app" / "ok.bin", 1000)
    locked = world.caches / "app" / "locked"
    make_file(locked / "secret.bin", 1000)
    locked.chmod(0)
    try:
        result, payload = scan(monkeypatch, world)
    finally:
        locked.chmod(0o755)

    assert result.exit_code == 0
    gaps = payload["meta"]["incomplete_coverage"]
    assert [(g["path"], g["reason"], g["errno"], g["operation"]) for g in gaps] == [
        (str(locked), "permission_denied", "EACCES", "scandir")
    ]
    assert payload["meta"]["status"] == "partial"


def test_unreadable_caches_root_is_a_coverage_gap(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    world.caches.chmod(0)
    try:
        result, payload = scan(monkeypatch, world)
    finally:
        world.caches.chmod(0o755)

    assert result.exit_code == 0
    assert payload["data"]["findings"] == []
    assert payload["meta"]["incomplete_coverage"][0]["operation"] == "scandir"


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_unusable_caches_root_is_an_empty_result(
    monkeypatch: pytest.MonkeyPatch, world: World, kind: str
) -> None:
    target = world.home / "nothing"
    if kind == "file":
        make_file(target, 10)
    install(monkeypatch, world)
    monkeypatch.setattr(
        caches,
        "default_environment",
        lambda: CachesEnvironment(
            str(world.home), str(target), world.environ, world.tools
        ),
    )
    result = CliRunner().invoke(main, ["caches", "scan"])
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["data"]["findings"] == []
    assert payload["data"]["summary"]["total_allocated_bytes"] == 0
    assert payload["meta"]["scope"]["roots"] == []
    expected = "not_installed" if kind == "missing" else "failed"
    sources = {u["source"]: u["reason"] for u in payload["meta"]["unavailable_sources"]}
    assert sources["caches"] == expected


def test_default_environment_reads_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/somewhere")
    env = caches.default_environment()
    assert (env.home, env.caches_root) == ("/somewhere", "/somewhere/Library/Caches")

    monkeypatch.delenv("HOME")
    env = caches.default_environment()
    assert (env.home, env.caches_root) == ("", "")
    offline = CachesEnvironment("", "", {}, FakeTools())
    assert caches.caches_scan(offline, 5).data.findings == ()


def test_default_tool_runner_uses_the_allowlisted_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Sequence[str]] = []

    def fake_run(argv: Sequence[str]) -> runner.RunResult:
        seen.append(argv)
        return run_result(argv, "/x\n")

    monkeypatch.setattr(runner, "run", fake_run)
    from byte_census.checks.tool_caches import default_tool_runner

    assert default_tool_runner(("uv", "cache", "dir")).stdout == "/x\n"
    assert seen == [("uv", "cache", "dir")]


def test_cost_counts_both_tool_calls_and_visited_entries(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    _, payload = scan(monkeypatch, world)

    cost = payload["meta"]["cost"]
    assert cost["subprocess_calls"] == 2
    assert cost["subprocess_stdout_bytes"] > 0
    assert cost["content_bytes_read"] == 0
    assert cost["entries_visited"] >= 10
    assert cost["subprocess_content_bytes_read"] is None


def test_rejected_argv_is_an_internal_error(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    world.tools.uv = runner.RejectedArgvError(("uv",), "not allowed")  # type: ignore[assignment]
    result, _ = scan(monkeypatch, world)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert json.loads(result.stderr)["code"] == "internal_error"


def test_unexpected_failure_exits_1(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    def boom(*_args: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(caches, "caches_scan", boom)
    result, _ = scan(monkeypatch, world)

    assert result.exit_code == 1
    assert json.loads(result.stderr)["help"] == "byte-census caches scan --help"


@pytest.mark.parametrize("args", [["--top", "0"], ["--top", "-1"], ["--top", "x"]])
def test_invalid_top_is_a_usage_error(args: list[str]) -> None:
    result = CliRunner().invoke(main, ["caches", "scan", *args])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert json.loads(result.stderr)["code"] == "usage_error"


def test_table_format(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    populate(world)
    install(monkeypatch, world)
    result = CliRunner().invoke(main, ["caches", "scan", "--format", "table"])

    assert result.exit_code == 0
    assert "big" in result.stdout
    assert "\x1b[" not in result.stdout


@pytest.mark.parametrize("flag", ["-h", "--help"])
@pytest.mark.parametrize("path", [["caches", "scan"], ["caches"]])
def test_help_has_usage_and_example(path: list[str], flag: str) -> None:
    result = CliRunner().invoke(main, [*path, flag])

    assert result.exit_code == 0
    assert result.stdout.startswith("Usage:")
    assert "Example:" in result.stdout


def test_output_is_deterministic(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    populate(world)
    first, _ = scan(monkeypatch, world)
    second, _ = scan(monkeypatch, world)
    a, b = json.loads(first.stdout), json.loads(second.stdout)
    for payload in (a, b):
        payload["meta"]["captured_at"] = payload["meta"]["cost"]["elapsed_s"] = None

    assert a == b


def test_dataless_caches_root_is_never_listed(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    make_file(world.caches / "app" / "f.bin", 1000)
    root = str(world.caches)
    real = caches.fsread.lstat

    def dataless(path: Any) -> Any:
        info = real(path)
        if os.fspath(path) != root:
            return info
        fields = {n: getattr(info, n) for n in dir(info) if n.startswith("st_")}
        return SimpleNamespace(**{**fields, "st_flags": 0x40000000})

    def forbidden(path: Any) -> Any:
        raise AssertionError(f"scandir called on {path}")

    monkeypatch.setattr(caches.fsread, "lstat", dataless)
    monkeypatch.setattr(caches.fsread.os, "scandir", forbidden)
    result, payload = scan(monkeypatch, world)

    assert result.exit_code == 0, result.stderr
    assert payload["data"]["findings"] == []
    assert payload["meta"]["status"] == "partial"
    assert payload["meta"]["incomplete_coverage"] == [
        {"path": root, "reason": "dataless", "errno": None, "operation": "scandir"}
    ]


def test_foreign_device_child_of_caches_is_a_skipped_mount(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    make_file(world.caches / "app" / "f.bin", 1000)
    make_file(world.caches / "mnt" / "g.bin", 1000)
    mount = str(world.caches / "mnt")
    real = caches.fsread.lstat

    def foreign(path: Any) -> Any:
        info = real(path)
        if os.fspath(path) != mount:
            return info
        fields = {n: getattr(info, n) for n in dir(info) if n.startswith("st_")}
        return SimpleNamespace(**{**fields, "st_dev": info.st_dev + 1})

    monkeypatch.setattr(caches.fsread, "lstat", foreign)
    _, payload = scan(monkeypatch, world)

    assert payload["meta"]["scope"]["skipped_mounts"] == [mount]
    assert mount not in by_target(payload)


def test_unreadable_npmrc_marks_the_npm_location_uncertain(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    make_file(world.home / ".npm" / "n.bin", 5000)
    os.mkfifo(world.home / ".npmrc")
    result, payload = scan(monkeypatch, world)

    assert result.exit_code == 0
    rc = str(world.home / ".npmrc")
    assert payload["meta"]["incomplete_coverage"] == [
        {"path": rc, "reason": "not_regular_file", "errno": None, "operation": "read"}
    ]
    assert payload["meta"]["status"] == "partial"
    npm = finding_for(payload, world.home / ".npm")
    assert rc in npm["details"]["location_uncertain"]
    assert "not_regular_file" in npm["details"]["location_uncertain"]


def test_unreadable_npmrc_is_reported_even_when_the_default_is_missing(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    populate(world)
    os.mkfifo(world.home / ".npmrc")
    _, payload = scan(monkeypatch, world)

    assert payload["meta"]["status"] == "partial"
    assert payload["meta"]["incomplete_coverage"][0]["path"] == str(
        world.home / ".npmrc"
    )


def test_hard_link_caveat_does_not_depend_on_measurement_order(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    original = make_file(world.caches / "zz" / "shared.bin", 5000)
    (world.caches / "aa").mkdir()
    os.link(original, world.caches / "aa" / "alias.bin")
    _, payload = scan(monkeypatch, world)

    for name in ("aa", "zz"):
        found = finding_for(payload, world.caches / name)
        assert "hard_links_merged" in found["caveats"]


def test_caches_root_swapped_after_listing_counts_nothing_outside(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    """Proof of concept: folders were re-walked by path after the listing."""
    make_file(world.caches / "big" / "a.bin", 10_000)
    outside = world.home / "outside"
    make_file(outside / "big" / "SECRET.bin", 5_000_000)
    real = caches._list_children

    def listing_then_swap(root: str) -> Any:
        found = real(root)
        os.rename(world.caches, world.caches.with_name("Caches-moved"))
        os.symlink(outside, world.caches)
        return found

    monkeypatch.setattr(caches, "_list_children", listing_then_swap)
    result, payload = scan(monkeypatch, world)

    assert result.exit_code == 0, result.stderr
    assert str(world.caches / "big") not in by_target(payload)
    assert all(f["allocated_bytes"] < 1_000_000 for f in payload["data"]["findings"])
    gaps = {g["path"]: g for g in payload["meta"]["incomplete_coverage"]}
    assert gaps[str(world.caches / "big")]["reason"] == "changed_during_scan"


def test_cache_folder_replaced_after_listing_is_a_changed_gap(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> None:
    make_file(world.caches / "big" / "a.bin", 10_000)
    make_file(world.caches / "keep" / "k.bin", 10_000)
    real = caches._list_children

    def listing_then_replace(root: str) -> Any:
        found = real(root)
        os.rename(world.caches / "big", world.caches / "big-old")
        make_file(world.caches / "big" / "new.bin", 20_000)
        return found

    monkeypatch.setattr(caches, "_list_children", listing_then_replace)
    _, payload = scan(monkeypatch, world)

    assert str(world.caches / "keep") in by_target(payload)
    assert str(world.caches / "big") not in by_target(payload)
    gaps = {g["path"]: g for g in payload["meta"]["incomplete_coverage"]}
    assert gaps[str(world.caches / "big")] == {
        "path": str(world.caches / "big"),
        "reason": "changed_during_scan",
        "errno": None,
        "operation": "scandir",
    }
