"""Tests for `byte-census docker scan` (WI-DOCKER).

Docker output is recorded JSON lines derived from the contract example; the
real docker binary is never run. A fake `run` stands in for the runner.
"""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from byte_census import runner
from byte_census.checks import docker as docker_check
from byte_census.checks.docker_sizes import (
    docker_created_at,
    parse_docker_size,
    parse_reclaimable,
)
from byte_census.cli import main
from byte_census.runner import (
    CommandTimeoutError,
    ExecutableNotFoundError,
    RunResult,
)
from tests.support.snapshots import assert_json_snapshot

CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "examples"
EXAMPLE = json.loads((CONTRACTS / "docker-scan.json").read_text(encoding="utf-8"))
ERROR_EXAMPLE = json.loads((CONTRACTS / "error.json").read_text(encoding="utf-8"))

DF = ("docker", "system", "df", "--format", "{{json .}}")
IMAGES = ("docker", "images", "--format", "{{json .}}")
DANGLING = ("docker", "images", "-f", "dangling=true", "-q")
PS = ("docker", "ps", "-a", "-f", "status=exited", "--format", "{{json .}}")


def _docker_time(iso: str) -> str:
    return iso.replace("T", " ").replace("Z", " +0000 UTC")


def df_lines() -> list[str]:
    lines = []
    for finding in EXAMPLE["data"]["findings"]:
        d = finding["details"]
        lines.append(
            json.dumps(
                {
                    "Type": d["docker_type"],
                    "TotalCount": str(d["total_count"]),
                    "Active": str(d["active_count"]),
                    "Size": d["raw"]["Size"],
                    "Reclaimable": d["raw"]["Reclaimable"],
                }
            )
        )
    return lines


def image_lines() -> list[str]:
    return [
        json.dumps(
            {
                "Repository": i["repository"],
                "Tag": i["tag"],
                "ID": i["image_id"],
                "Size": i["raw_size"],
                "CreatedAt": _docker_time(i["created_at"]),
            }
        )
        for i in EXAMPLE["data"]["images"]
    ]


def ps_lines() -> list[str]:
    return [
        json.dumps(
            {
                "Names": c["name"],
                "Image": c["image"],
                "ID": c["container_id"],
                "Status": c["status"],
                "CreatedAt": _docker_time(c["created_at"]),
            }
        )
        for c in EXAMPLE["data"]["stopped_containers"]
    ]


def ok(argv: Sequence[str], lines: Sequence[str]) -> RunResult:
    out = "".join(line + "\n" for line in lines)
    return RunResult(tuple(argv), "/fake/docker", 0, out, "", len(out.encode()))


def bad(argv: Sequence[str], code: int = 1, err: str = "boom") -> RunResult:
    return RunResult(tuple(argv), "/fake/docker", code, "", err, 0)


def responses(**overrides: Any) -> dict[tuple[str, ...], Any]:
    base = {
        DF: ok(DF, df_lines()),
        IMAGES: ok(IMAGES, image_lines()),
        DANGLING: ok(DANGLING, ["9a41c0e6b2d8"]),
        PS: ok(PS, ps_lines()),
    }
    names = {"df": DF, "images": IMAGES, "dangling": DANGLING, "ps": PS}
    return {**base, **{names[k]: v for k, v in overrides.items()}}


def fake_run(table: dict[tuple[str, ...], Any]) -> Callable[[Sequence[str]], RunResult]:
    calls: list[tuple[str, ...]] = []

    def run(argv: Sequence[str]) -> RunResult:
        key = tuple(argv)
        calls.append(key)
        value = table[key]
        if isinstance(value, Exception):
            raise value
        return value

    run.calls = calls  # type: ignore[attr-defined]
    return run


def invoke(monkeypatch: pytest.MonkeyPatch, table: dict, args: list[str] | None = None):
    monkeypatch.setattr(docker_check, "run_allowlisted", fake_run(table))
    return CliRunner().invoke(main, ["docker", "scan", *(args or [])])


def test_sizes_use_decimal_base_exactly() -> None:
    assert parse_docker_size("7.42GB") == 7_420_000_000
    assert parse_docker_size("184.6MB") == 184_600_000
    assert parse_docker_size("438MB") == 438_000_000
    assert parse_docker_size("1.5kB") == 1_500
    assert parse_docker_size("0B") == 0
    assert parse_docker_size("2TB") == 2_000_000_000_000
    assert parse_docker_size("1.23456789GB") == 1_234_567_890


@pytest.mark.parametrize("raw", ["", "12", "GB", "1.2.3GB", "-4MB", "5 apples"])
def test_unparseable_sizes_are_none(raw: str) -> None:
    assert parse_docker_size(raw) is None


def test_reclaimable_drops_the_percentage() -> None:
    assert parse_reclaimable("3.18GB (42%)") == 3_180_000_000
    assert parse_reclaimable("1.87GB") == 1_870_000_000


def test_created_at_is_normalized_to_utc() -> None:
    assert docker_created_at("2026-06-02 15:40:03 +0000 UTC") == "2026-06-02T15:40:03Z"
    assert docker_created_at("2026-06-02 17:40:03 +0200 CEST") == "2026-06-02T15:40:03Z"
    assert docker_created_at("not a date") == "not a date"


def test_happy_path_matches_the_contract_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = invoke(monkeypatch, responses())

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"] == EXAMPLE["data"]
    assert list(payload["data"]) == list(EXAMPLE["data"])
    assert payload["meta"]["command"] == "docker scan"
    assert payload["meta"]["status"] == "complete"
    assert payload["meta"]["cost"]["subprocess_calls"] == 4
    assert payload["meta"]["scope"] == EXAMPLE["meta"]["scope"]


def test_happy_path_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(monkeypatch, responses())

    assert_json_snapshot(json.loads(result.output), "docker-scan")


def test_only_the_four_allowlisted_argvs_run(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = fake_run(responses())
    monkeypatch.setattr(docker_check, "run_allowlisted", fake)

    CliRunner().invoke(main, ["docker", "scan"])

    assert fake.calls == [DF, IMAGES, DANGLING, PS]  # type: ignore[attr-defined]
    for argv in fake.calls:  # type: ignore[attr-defined]
        runner.match_template(list(argv))


def test_docker_figures_never_reach_host_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.loads(invoke(monkeypatch, responses()).output)

    for finding in payload["data"]["findings"]:
        assert finding["logical_bytes"] is None
        assert finding["allocated_bytes"] is None
        assert finding["reclaimable_estimate_bytes"] is None
        assert finding["caveats"] == ["docker_reported_not_host"]
    assert payload["data"]["summary"]["informational"] is True


def test_volumes_relate_only_to_volume_prune(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(invoke(monkeypatch, responses()).output)

    volume = next(
        f for f in payload["data"]["findings"] if f["target"] == "docker:Local Volumes"
    )
    assert volume["suggestion_ids"] == ["docker-volume-prune"]
    prune_all = next(
        s
        for s in payload["data"]["suggestions"]
        if s["id"] == "docker-system-prune-all"
    )
    assert volume["id"] not in prune_all["finding_ids"]


def test_suggestion_risks(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(invoke(monkeypatch, responses()).output)

    risks = {s["id"]: s["risk"] for s in payload["data"]["suggestions"]}
    assert risks == {
        "docker-image-prune": "low",
        "docker-container-prune": "medium",
        "docker-system-prune-all": "high",
        "docker-volume-prune": "high",
    }


def test_only_related_suggestions_are_emitted(monkeypatch: pytest.MonkeyPatch) -> None:
    only_volumes = [line for line in df_lines() if "Local Volumes" in line]
    table = responses(df=ok(DF, only_volumes))

    payload = json.loads(invoke(monkeypatch, table).output)

    assert [s["id"] for s in payload["data"]["suggestions"]] == ["docker-volume-prune"]


def test_images_and_containers_are_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    table = responses(
        images=ok(IMAGES, list(reversed(image_lines()))),
        ps=ok(PS, list(reversed(ps_lines()))),
    )

    payload = json.loads(invoke(monkeypatch, table).output)

    assert [i["repository"] for i in payload["data"]["images"]] == [
        "<none>",
        "postgres",
        "python",
    ]
    assert [c["name"] for c in payload["data"]["stopped_containers"]] == [
        "api-db-1",
        "scratch-run",
    ]


def test_no_dangling_images_counts_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.loads(
        invoke(monkeypatch, responses(dangling=ok(DANGLING, []))).output
    )

    assert payload["data"]["summary"]["dangling_image_count"] == 0


def test_table_format_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(monkeypatch, responses(), ["--format", "table"])

    assert result.exit_code == 0
    assert "docker:Images" in result.output


def error_object(result: Any) -> dict[str, Any]:
    assert result.stdout == ""
    return json.loads(result.stderr)


def test_daemon_down_exits_4_with_the_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    msg = "Cannot connect to the Docker daemon. Is the docker daemon running?"
    result = invoke(monkeypatch, responses(df=bad(DF, 1, msg)))

    assert result.exit_code == 4
    assert error_object(result) == ERROR_EXAMPLE


def test_missing_cli_exits_4_with_a_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = ExecutableNotFoundError(DF, "docker is not installed")
    result = invoke(monkeypatch, responses(df=missing))

    error = error_object(result)
    assert result.exit_code == 4
    assert error["code"] == "source_unavailable"
    assert error["exit_code"] == 4
    assert error["error"] == "docker scan could not read Docker disk usage"
    assert "not installed" in error["reason"]
    assert "Install Docker" in error["suggestion"]
    assert error["help"] == "byte-census docker scan --help"


def test_df_timeout_exits_4(monkeypatch: pytest.MonkeyPatch) -> None:
    timeout = CommandTimeoutError(DF, "docker timed out after 120 s", 120)
    result = invoke(monkeypatch, responses(df=timeout))

    assert result.exit_code == 4
    assert "timed out" in error_object(result)["reason"]


def test_unreadable_df_output_exits_4(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(monkeypatch, responses(df=ok(DF, ["not json"])))

    assert result.exit_code == 4
    assert "not valid JSON" in error_object(result)["reason"]


@pytest.mark.parametrize(
    ("key", "source", "reason"),
    [
        ("images", "docker images", "failed"),
        ("dangling", "docker images -f dangling=true -q", "failed"),
        ("ps", "docker ps -a -f status=exited", "failed"),
    ],
)
def test_optional_source_failure_makes_the_result_partial(
    monkeypatch: pytest.MonkeyPatch, key: str, source: str, reason: str
) -> None:
    result = invoke(monkeypatch, responses(**{key: bad(("docker",))}))

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["meta"]["status"] == "partial"
    assert payload["meta"]["unavailable_sources"][0]["source"] == source
    assert payload["meta"]["unavailable_sources"][0]["reason"] == reason


def test_optional_source_timeout_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    timeout = CommandTimeoutError(PS, "docker timed out after 120 s", 120)

    payload = json.loads(invoke(monkeypatch, responses(ps=timeout)).output)

    assert payload["meta"]["unavailable_sources"][0]["reason"] == "timed_out"
    assert payload["data"]["stopped_containers"] == []


def test_unparseable_image_line_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    table = responses(images=ok(IMAGES, ["{broken"]))

    payload = json.loads(invoke(monkeypatch, table).output)

    assert payload["meta"]["status"] == "partial"
    assert payload["data"]["images"] == []


def test_unknown_type_is_kept_and_listed_after_known_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    line = json.dumps(
        {
            "Type": "Mystery",
            "TotalCount": "3",
            "Active": "1",
            "Size": "1MB",
            "Reclaimable": "0B",
        }
    )
    table = responses(df=ok(DF, [*df_lines(), line]))

    payload = json.loads(invoke(monkeypatch, table).output)

    mystery = payload["data"]["findings"][-1]
    assert mystery["target"] == "docker:Mystery"
    assert mystery["suggestion_ids"] == []
    assert payload["meta"]["status"] == "complete"


@pytest.mark.parametrize(
    "lines",
    [[], ["{}"], ['{"Type": "Images"}'], ['{"Size": "1MB", "Reclaimable": "0B"}']],
    ids=["empty", "empty-object", "missing-fields", "missing-type"],
)
def test_unusable_df_output_exits_4(
    monkeypatch: pytest.MonkeyPatch, lines: list[str]
) -> None:
    result = invoke(monkeypatch, responses(df=ok(DF, lines)))

    error = error_object(result)
    assert result.exit_code == 4
    assert error["error"] == "docker scan could not read Docker disk usage"
    assert "unusable" in error["reason"]


def test_df_rows_missing_fields_are_dropped_and_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = responses(df=ok(DF, [*df_lines(), '{"Type": "Mystery"}']))

    payload = json.loads(invoke(monkeypatch, table).output)

    assert len(payload["data"]["findings"]) == 4
    assert payload["meta"]["status"] == "partial"
    source = payload["meta"]["unavailable_sources"][0]
    assert source["source"] == "docker system df"
    assert "Mystery" in source["detail"]
    assert "TotalCount" in source["detail"]


def test_unparseable_numbers_are_null_raw_kept_and_totals_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_row = json.dumps(
        {
            "Type": "Images",
            "TotalCount": "x",
            "Active": "1",
            "Size": "?",
            "Reclaimable": "?",
        }
    )
    others = [line for line in df_lines() if '"Images"' not in line]
    table = responses(df=ok(DF, [bad_row, *others]))

    payload = json.loads(invoke(monkeypatch, table).output)

    details = payload["data"]["findings"][0]["details"]
    assert details["total_count"] is None
    assert details["docker_reported_size_bytes"] is None
    assert details["raw"] == {
        "Size": "?",
        "Reclaimable": "?",
        "TotalCount": "x",
    }
    summary = payload["data"]["summary"]
    assert summary["docker_reported_size_bytes"] is None
    assert summary["docker_reported_reclaimable_bytes"] is None
    assert payload["meta"]["status"] == "partial"
    detail = payload["meta"]["unavailable_sources"][0]["detail"]
    assert "Images" in detail
    assert "Size" in detail
    assert "TotalCount" in detail


@pytest.mark.parametrize(
    ("key", "argv", "lines"),
    [
        ("images", IMAGES, ["{}"]),
        ("images", IMAGES, ['{"Repository": "x"}']),
        ("ps", PS, ["{}"]),
        ("ps", PS, ['{"Names": "x"}']),
        ("dangling", DANGLING, ["not an id"]),
    ],
)
def test_unusable_optional_data_is_an_unavailable_source(
    monkeypatch: pytest.MonkeyPatch, key: str, argv: tuple[str, ...], lines: list[str]
) -> None:
    result = invoke(monkeypatch, responses(**{key: ok(argv, lines)}))

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["meta"]["status"] == "partial"
    assert payload["meta"]["unavailable_sources"][0]["reason"] == "failed"
    assert payload["data"]["images" if key == "images" else "stopped_containers"] in (
        [],
        EXAMPLE["data"]["images"],
        EXAMPLE["data"]["stopped_containers"],
    )


def test_unparseable_image_size_is_null_and_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = json.dumps(
        {"Repository": "r", "Tag": "t", "ID": "abc123", "Size": "?", "CreatedAt": "x"}
    )

    payload = json.loads(
        invoke(monkeypatch, responses(images=ok(IMAGES, [row]))).output
    )

    assert payload["data"]["images"][0]["docker_reported_size_bytes"] is None
    assert payload["data"]["images"][0]["raw_size"] == "?"
    assert payload["meta"]["status"] == "partial"


HUGE = "9" * 5000


def test_huge_size_string_is_unparseable_not_a_crash() -> None:
    assert parse_docker_size(HUGE + "GB") is None
    assert parse_docker_size("1." + HUGE + "GB") is None
    assert parse_reclaimable(HUGE + "GB (1%)") is None


def test_invalid_calendar_date_keeps_the_raw_text() -> None:
    raw = "2026-13-45 99:99:99 +0000 UTC"
    assert docker_created_at(raw) == raw


def test_huge_size_in_df_is_null_and_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = json.dumps(
        {"Type": "Images", "TotalCount": "1", "Size": HUGE + "GB", "Reclaimable": "0B"}
    )
    others = [line for line in df_lines() if '"Images"' not in line]

    result = invoke(monkeypatch, responses(df=ok(DF, [row, *others])))

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert (
        payload["data"]["findings"][0]["details"]["docker_reported_size_bytes"] is None
    )
    assert payload["meta"]["status"] == "partial"


HUGE_INT_LINE = '{"Type": "Images", "TotalCount": ' + HUGE + "}"
DEEP_LINE = "[" * 100000


@pytest.mark.parametrize("line", [HUGE_INT_LINE, DEEP_LINE], ids=["bigint", "deep"])
def test_malformed_df_json_exits_4(monkeypatch: pytest.MonkeyPatch, line: str) -> None:
    result = invoke(monkeypatch, responses(df=ok(DF, [line])))

    assert result.exit_code == 4
    assert error_object(result)["code"] == "source_unavailable"


@pytest.mark.parametrize("line", [HUGE_INT_LINE, DEEP_LINE], ids=["bigint", "deep"])
def test_malformed_optional_json_is_an_unavailable_source(
    monkeypatch: pytest.MonkeyPatch, line: str
) -> None:
    result = invoke(monkeypatch, responses(images=ok(IMAGES, [line])))

    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["meta"]["status"] == "partial"
    assert payload["data"]["images"] == []


def test_invalid_date_marks_the_source_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = json.dumps(
        {
            "Names": "n",
            "Image": "i",
            "ID": "abc123",
            "Status": "Exited",
            "CreatedAt": "2026-13-45 99:99:99 +0000 UTC",
        }
    )

    payload = json.loads(invoke(monkeypatch, responses(ps=ok(PS, [row]))).output)

    container = payload["data"]["stopped_containers"][0]
    assert container["created_at"] == "2026-13-45 99:99:99 +0000 UTC"
    assert payload["meta"]["status"] == "partial"
    assert payload["meta"]["unavailable_sources"][0]["source"].startswith("docker ps")


def df_row(**fields: str) -> str:
    base = {"Type": "Images", "TotalCount": "1", "Size": "1MB", "Reclaimable": "0B"}
    return json.dumps({**base, **fields})


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
def test_blank_type_row_is_dropped_and_partial(
    monkeypatch: pytest.MonkeyPatch, blank: str
) -> None:
    table = responses(df=ok(DF, [*df_lines(), df_row(Type=blank)]))

    payload = json.loads(invoke(monkeypatch, table).output)

    assert len(payload["data"]["findings"]) == 4
    assert payload["meta"]["status"] == "partial"
    assert "empty Type" in payload["meta"]["unavailable_sources"][0]["detail"]


def test_only_blank_type_rows_exit_4(monkeypatch: pytest.MonkeyPatch) -> None:
    result = invoke(monkeypatch, responses(df=ok(DF, [df_row(Type=" ")])))

    assert result.exit_code == 4
    assert "unusable" in error_object(result)["reason"]


@pytest.mark.parametrize("raw", ["-1", "x", "1.5", ""])
@pytest.mark.parametrize("field", ["TotalCount", "Active"])
def test_bad_counts_are_null_raw_kept_and_partial(
    monkeypatch: pytest.MonkeyPatch, field: str, raw: str
) -> None:
    others = [line for line in df_lines() if '"Images"' not in line]
    row = df_row(**{field: raw, "Active": raw if field == "Active" else "1"})
    payload = json.loads(
        invoke(monkeypatch, responses(df=ok(DF, [row, *others]))).output
    )

    details = payload["data"]["findings"][0]["details"]
    key = "total_count" if field == "TotalCount" else "active_count"
    assert details[key] is None
    assert details["raw"][field] == raw
    assert payload["meta"]["status"] == "partial"
    assert field in payload["meta"]["unavailable_sources"][0]["detail"]


def test_zero_counts_are_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    row = df_row(TotalCount="0", Active="0")

    payload = json.loads(invoke(monkeypatch, responses(df=ok(DF, [row]))).output)

    assert payload["data"]["findings"][0]["details"]["total_count"] == 0
    assert payload["meta"]["status"] == "complete"


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_has_usage_and_example(flag: str) -> None:
    result = CliRunner().invoke(main, ["docker", "scan", flag])

    assert result.exit_code == 0
    assert result.output.startswith("Usage:")
    assert "Example:" in result.output


def test_group_help_lists_scan() -> None:
    result = CliRunner().invoke(main, ["docker", "--help"])

    assert result.exit_code == 0
    assert "scan" in result.output
    assert "Example:" in result.output


def test_unknown_option_exits_2() -> None:
    result = CliRunner().invoke(main, ["docker", "scan", "--bogus"])

    assert result.exit_code == 2
    assert json.loads(result.stderr)["code"] == "usage_error"


def test_default_runner_goes_through_the_allowlist() -> None:
    with pytest.raises(runner.RejectedArgvError):
        docker_check.run_allowlisted(["docker", "system", "prune"])
