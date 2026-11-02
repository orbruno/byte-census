"""Every help block quoted in README.md must match the live --help output."""

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from byte_census.cli import main

README = Path(__file__).resolve().parents[1] / "README.md"
BLOCK = re.compile(
    r"<!-- help: byte-census([^>]*?) -->\n```text\n(.*?)\n```", re.DOTALL
)


def _normalize(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def _blocks() -> list[tuple[list[str], str]]:
    return [
        (match.group(1).split(), match.group(2))
        for match in BLOCK.finditer(README.read_text(encoding="utf-8"))
    ]


def test_readme_quotes_help_for_every_command() -> None:
    quoted = {" ".join(args) for args, _ in _blocks()}

    assert quoted == {
        "",
        "docker scan",
        "caches scan",
        "artifacts scan",
        "duplicates scan",
        "disk map",
    }


@pytest.mark.parametrize(
    ("args", "quoted"),
    _blocks(),
    ids=lambda v: " ".join(v) if isinstance(v, list) else "",
)
def test_readme_help_block_matches_live_help(args: list[str], quoted: str) -> None:
    result = CliRunner().invoke(main, [*args, "--help"])

    assert result.exit_code == 0
    assert _normalize(quoted) == _normalize(result.output)
