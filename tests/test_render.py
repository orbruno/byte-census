"""JSON and table rendering, TTY and NO_COLOR rules (WI-CORE AC-06)."""

import io
import json
from pathlib import Path

import pytest

from byte_census.render import color_enabled, render
from byte_census.render.table_format import format_bytes, render_table

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "contracts" / "examples"
ANSI = "\x1b["


class FakeStream(io.StringIO):
    def __init__(self, tty: bool) -> None:
        super().__init__()
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


def example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def test_json_render_round_trips_in_order() -> None:
    raw = example("duplicates-scan")

    text = render(raw, "json", color=True)

    assert text.endswith("\n")
    assert json.loads(text) == raw
    assert list(json.loads(text)) == ["data", "meta"]
    assert ANSI not in text


def test_json_keeps_non_ascii_text() -> None:
    text = render({"data": {"p": "/Users/é"}}, "json", color=False)

    assert "/Users/é" in text


def test_unknown_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="format"):
        render({}, "csv", color=False)


@pytest.mark.parametrize(
    "name",
    ["artifacts-scan", "caches-scan", "disk-map", "docker-scan", "duplicates-scan"],
)
def test_table_renders_every_example_without_ansi(name: str) -> None:
    raw = example(name)

    text = render(raw, "table", color=False)

    assert ANSI not in text
    assert raw["meta"]["command"] in text
    assert f"status: {raw['meta']['status']}" in text
    assert "Findings" in text


def test_table_shows_findings_suggestions_coverage_and_cost() -> None:
    text = render_table(example("duplicates-scan"), color=False)

    assert "duplicate_group" in text
    assert "4.8 MiB" in text
    assert "high" in text
    assert "rm -- " in text
    assert "dataless" in text
    assert "Incomplete coverage (2)" in text
    assert "0.734 s" in text


def test_table_truncates_long_coverage_list() -> None:
    raw = example("duplicates-scan")
    entries = [
        {
            "path": f"/p/{i:03}",
            "reason": "vanished",
            "errno": None,
            "operation": "lstat",
        }
        for i in range(30)
    ]
    raw["meta"]["incomplete_coverage"] = entries

    text = render_table(raw, color=False)

    assert "/p/019" in text
    assert "/p/020" not in text
    assert "10 more" in text


def test_table_with_color_uses_ansi() -> None:
    assert ANSI in render_table(example("duplicates-scan"), color=True)


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (None, "-"),
        (0, "0 B"),
        (1023, "1023 B"),
        (1024, "1.0 KiB"),
        (5005312, "4.8 MiB"),
        (7_420_000_000, "6.9 GiB"),
        (3 * 1024**4, "3.0 TiB"),
    ],
)
def test_format_bytes(value: int | None, text: str) -> None:
    assert format_bytes(value) == text


@pytest.mark.parametrize(
    ("tty", "environ", "expected"),
    [
        (True, {}, True),
        (False, {}, False),
        (True, {"NO_COLOR": "1"}, False),
        (False, {"NO_COLOR": "1"}, False),
        (True, {"NO_COLOR": ""}, True),
    ],
)
def test_color_enabled_rules(tty: bool, environ: dict, expected: bool) -> None:
    assert color_enabled(FakeStream(tty), environ) is expected


def test_color_disabled_when_stream_has_no_isatty() -> None:
    assert color_enabled(object(), {}) is False
