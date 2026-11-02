"""End-to-end command scaffold through the hidden _selftest command.

Covers every exit-code path, JSON errors on stderr (including Click usage
errors), the default JSON format, `--format table`, TTY and NO_COLOR, and
the no-prompt rule (WI-CORE AC-01, AC-03 to AC-07).
"""

import json
import os
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner, Result

from byte_census import command
from byte_census.cli import main
from tests.support.snapshots import assert_json_snapshot

ANSI = "\x1b["
ERROR_KEYS = [
    "schema_version",
    "error",
    "reason",
    "suggestion",
    "help",
    "code",
    "exit_code",
]


def invoke(args: list[str], **kwargs: Any) -> Result:
    return CliRunner().invoke(main, args, **kwargs)


def error_of(result: Result) -> dict[str, Any]:
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert list(payload) == ERROR_KEYS
    assert payload["exit_code"] == result.exit_code
    assert "Traceback" not in result.stderr
    return payload


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("a")
    (root / "sub" / "b.txt").write_text("b")
    return root


def test_selftest_defaults_to_json_envelope(tree: Path) -> None:
    result = invoke(["_selftest", "--root", str(tree)])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    meta = payload["meta"]
    assert list(payload) == ["data", "meta"]
    assert meta["command"] == "_selftest"
    assert meta["status"] == "complete"
    assert meta["captured_at"].endswith("Z")
    assert meta["scope"]["roots"] == [
        {
            "path": str(tree.resolve()),
            "given": str(tree),
            "st_dev": os.stat(tree).st_dev,
        }
    ]
    assert meta["cost"]["entries_visited"] == 3
    assert meta["cost"]["subprocess_content_bytes_read"] == 0
    assert isinstance(meta["cost"]["elapsed_s"], float)
    finding = payload["data"]["findings"][0]
    assert finding["suggestion_ids"] == [payload["data"]["suggestions"][0]["id"]]
    assert finding["classification"]["disposition"] == "investigate"


def test_selftest_snapshot_is_stable(tree: Path) -> None:
    result = invoke(["_selftest", "--root", str(tree)])

    assert_json_snapshot(
        json.loads(result.stdout), "selftest", roots=[tree, tree.resolve()]
    )


def test_selftest_without_root_has_empty_scope() -> None:
    result = invoke(["_selftest"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["meta"]["scope"]["roots"] == []


def test_partial_coverage_exits_zero_with_status_partial(tree: Path) -> None:
    result = invoke(["_selftest", "--root", str(tree), "--partial"])

    assert result.exit_code == 0
    meta = json.loads(result.stdout)["meta"]
    assert meta["status"] == "partial"
    assert meta["incomplete_coverage"][0]["reason"] == "vanished"


def test_walk_errors_become_incomplete_coverage(tree: Path) -> None:
    locked = tree / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        result = invoke(["_selftest", "--root", str(tree)])
    finally:
        locked.chmod(0o755)

    meta = json.loads(result.stdout)["meta"]
    assert result.exit_code == 0
    assert meta["status"] == "partial"
    assert meta["incomplete_coverage"][0]["path"] == str(tree.resolve() / "locked")


@pytest.mark.parametrize(
    "args",
    [
        ["_selftest", "--bogus"],
        ["_selftest", "--format", "csv"],
        ["_selftest", "--fail", "nope"],
        ["_selftest", "extra-argument"],
        ["no-such-command"],
        ["--bogus"],
    ],
)
def test_usage_errors_exit_2_as_json(args: list[str]) -> None:
    result = invoke(args)

    assert result.exit_code == 2
    payload = error_of(result)
    assert payload["code"] == "usage_error"
    assert payload["help"].endswith("--help")


def test_usage_error_help_names_the_subcommand() -> None:
    payload = error_of(invoke(["_selftest", "--bogus"]))

    assert payload["help"] == "byte-census _selftest --help"
    assert "--bogus" in payload["reason"]


@pytest.mark.parametrize("bad", ["/definitely/not/here", "bad\x01name"])
def test_validation_error_exits_3(bad: str) -> None:
    result = invoke(["_selftest", "--root", bad])

    assert result.exit_code == 3
    payload = error_of(result)
    assert payload["code"] == "validation_error"
    assert payload["help"] == "byte-census _selftest --help"


def test_root_that_is_a_file_exits_3(tree: Path) -> None:
    result = invoke(["_selftest", "--root", str(tree / "a.txt")])

    assert result.exit_code == 3


def test_source_unavailable_exits_4() -> None:
    result = invoke(["_selftest", "--fail", "unavailable"])

    assert result.exit_code == 4
    payload = error_of(result)
    assert payload["code"] == "source_unavailable"


def test_internal_error_exits_1_without_traceback() -> None:
    result = invoke(["_selftest", "--fail", "internal"])

    assert result.exit_code == 1
    payload = error_of(result)
    assert payload["code"] == "internal_error"
    assert "RuntimeError" in payload["reason"]


def test_interrupt_exits_1_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(**_: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(command, "_default_now", interrupt)

    result = invoke(["_selftest"])

    assert result.exit_code == 1
    assert json.loads(result.stderr.strip())["code"] == "internal_error"


def test_help_and_version_still_exit_zero() -> None:
    assert invoke(["--help"]).exit_code == 0
    assert invoke(["_selftest", "--help"]).exit_code == 0
    assert invoke(["--version"]).stdout.strip() == "byte-census 2.0.0"


def test_selftest_is_hidden_from_help() -> None:
    assert "_selftest" not in invoke(["--help"]).stdout


def test_standalone_mode_false_returns_without_exit() -> None:
    rv = main.main(["_selftest", "--help"], standalone_mode=False)

    assert rv == 0


def test_table_format_has_no_ansi_without_tty(tree: Path) -> None:
    result = invoke(["_selftest", "--root", str(tree), "--format", "table"], color=True)

    assert result.exit_code == 0
    assert "_selftest" in result.stdout
    assert ANSI not in result.stdout


def test_table_format_has_ansi_on_tty(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(command, "stdout_is_tty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)

    result = invoke(["_selftest", "--format", "table"], color=True)

    assert ANSI in result.stdout


def test_no_color_disables_ansi_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(command, "stdout_is_tty", lambda: True)

    result = invoke(
        ["_selftest", "--format", "table"], color=True, env={"NO_COLOR": "1"}
    )

    assert result.exit_code == 0
    assert ANSI not in result.stdout


def test_json_has_no_ansi_on_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(command, "stdout_is_tty", lambda: True)

    result = invoke(["_selftest"], color=True)

    assert ANSI not in result.stdout


def test_stdout_is_tty_reads_stdout() -> None:
    assert command.stdout_is_tty() in (True, False)


def test_cli_never_reads_stdin(tree: Path) -> None:
    result = invoke(["_selftest", "--root", str(tree)], input="y\n" * 5)

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["summary"]["entries"] == 3


def _all_commands(cmd: click.Command, path: str = "byte-census"):
    yield path, cmd
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            yield from _all_commands(sub, f"{path} {name}")


def test_no_command_prompts_and_every_option_has_a_flag() -> None:
    for path, cmd in _all_commands(main):
        for param in cmd.params:
            if isinstance(param, click.Option):
                assert not param.prompt, (path, param.name)
                assert not param.confirmation_prompt, (path, param.name)
                assert any(opt.startswith("--") for opt in param.opts), (path, param)
