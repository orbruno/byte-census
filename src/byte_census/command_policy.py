"""External command policy: argv allowlist, executables, and child environment.

This module only describes what may run; `byte_census.runner` runs it. The
table mirrors docs/contracts/argv-allowlist.md exactly.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Operand:
    """A variable argv slot that accepts only the listed constant values."""

    name: str
    allowed: frozenset[str]

    def accepts(self, token: str) -> bool:
        return token in self.allowed


DF_MOUNT_POINT = _Operand("PATH", frozenset({"/", "/System/Volumes/Data"}))
JSON_FORMAT = "{{json .}}"

Token = str | _Operand


@dataclass(frozen=True)
class CommandTemplate:
    """One row of the argv allowlist."""

    tokens: tuple[Token, ...]
    timeout_s: int

    def matches(self, argv: Sequence[str]) -> bool:
        if len(argv) != len(self.tokens):
            return False
        return all(
            token.accepts(value) if isinstance(token, _Operand) else token == value
            for token, value in zip(self.tokens, argv, strict=True)
        )


@dataclass(frozen=True)
class CommandSpec:
    """One concrete argv the allowlist permits, with its timeout."""

    argv: tuple[str, ...]
    timeout_s: int


TEMPLATES: tuple[CommandTemplate, ...] = (
    CommandTemplate(("docker", "system", "df", "--format", JSON_FORMAT), 120),
    CommandTemplate(("docker", "images", "--format", JSON_FORMAT), 120),
    CommandTemplate(("docker", "images", "-f", "dangling=true", "-q"), 120),
    CommandTemplate(
        ("docker", "ps", "-a", "-f", "status=exited", "--format", JSON_FORMAT), 120
    ),
    CommandTemplate(("uv", "cache", "dir"), 60),
    CommandTemplate(("npm", "config", "get", "cache"), 60),
    CommandTemplate(("brew", "--cache"), 60),
    CommandTemplate(("df", "-k", DF_MOUNT_POINT), 60),
    CommandTemplate(("diskutil", "info", "/"), 60),
    CommandTemplate(("tmutil", "listlocalsnapshots", "/"), 60),
)


def _expand(template: CommandTemplate) -> tuple[CommandSpec, ...]:
    """List every concrete argv a template permits."""
    combos: list[tuple[str, ...]] = [()]
    for token in template.tokens:
        values = sorted(token.allowed) if isinstance(token, _Operand) else [token]
        combos = [prefix + (value,) for prefix in combos for value in values]
    return tuple(CommandSpec(argv, template.timeout_s) for argv in combos)


ALLOWED_COMMANDS: tuple[CommandSpec, ...] = tuple(
    spec for template in TEMPLATES for spec in _expand(template)
)

# System tools are never looked up on PATH, so an empty or relative PATH entry
# cannot substitute them.
PINNED_EXECUTABLES: Mapping[str, str] = {
    "df": "/bin/df",
    "diskutil": "/usr/sbin/diskutil",
    "tmutil": "/usr/bin/tmutil",
}

BASE_PASSTHROUGH: tuple[str, ...] = ("PATH", "HOME", "USER", "TMPDIR")

# Variables that change where a tool's cache or daemon is, so the answer
# matches what the user's own shell would report.
TOOL_PASSTHROUGH: Mapping[str, tuple[str, ...]] = {
    "docker": ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"),
    "uv": ("UV_CACHE_DIR", "XDG_CACHE_HOME"),
    "npm": ("npm_config_cache", "NPM_CONFIG_CACHE"),
    "brew": ("HOMEBREW_CACHE",),
}

# Settings that switch off each tool's own writes (see argv-allowlist.md).
TOOL_SETTINGS: Mapping[str, Mapping[str, str]] = {
    "docker": {"DOCKER_CLI_HINTS": "false"},
    "npm": {"npm_config_logs_max": "0", "npm_config_update_notifier": "false"},
    "brew": {
        "HOMEBREW_NO_AUTO_UPDATE": "1",
        "HOMEBREW_NO_ANALYTICS": "1",
        "HOMEBREW_NO_ENV_HINTS": "1",
    },
}


def child_environment(tool: str, environ: Mapping[str, str]) -> dict[str, str]:
    """Build the minimal explicit environment for one tool."""
    names = BASE_PASSTHROUGH + TOOL_PASSTHROUGH.get(tool, ())
    kept = {name: environ[name] for name in names if name in environ}
    return {**kept, "LC_ALL": "C", **TOOL_SETTINGS.get(tool, {})}


def is_string_argv(argv: Any) -> bool:
    """Report whether argv is a non-string sequence of strings."""
    if isinstance(argv, (str, bytes)):
        return False
    return all(isinstance(token, str) for token in argv)


def find_template(argv: Sequence[str]) -> CommandTemplate | None:
    """Return the allowlist row argv matches exactly, if any."""
    return next((t for t in TEMPLATES if t.matches(argv)), None)
