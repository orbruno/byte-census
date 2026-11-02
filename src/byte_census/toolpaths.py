"""Tool cache locations resolved by reading configuration, never by running a tool.

npm is not in the process allowlist: every npm invocation writes or deletes
debug logs and may create its cache directory. Its cache location is read
from, in order: the `npm_config_cache` environment variable (matched
case-insensitively, as npm does), a `cache=` line in `$HOME/.npmrc`, and the
default `$HOME/.npm`. Global and project npmrc files are not consulted.
Nothing is created.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from byte_census.fsread import FsReadError, read_small_file

NPMRC_MAX_BYTES = 1024 * 1024
NPM_CACHE_KEY = "npm_config_cache"


@dataclass(frozen=True)
class ToolPath:
    """A resolved location and the source that decided it."""

    path: str | None
    source: str
    note: str | None


def _expand(value: str, home: str) -> str:
    expanded = value.replace("${HOME}", home)
    if expanded == "~" or expanded.startswith("~/"):
        return home + expanded[1:]
    return expanded


def _environment_value(environ: Mapping[str, str]) -> tuple[str, str] | None:
    names = sorted(
        (name for name in environ if name.lower() == NPM_CACHE_KEY),
        key=lambda name: (name != NPM_CACHE_KEY, name),
    )
    for name in names:
        if environ[name]:
            return name, environ[name]
    return None


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_npmrc_cache(text: str) -> str | None:
    """Return the last non-empty `cache=` value in npmrc text, if any."""
    found: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;" or "=" not in line:
            continue
        key, _, value = line.partition("=")
        cleaned = _unquote(value.strip())
        if key.strip() == "cache" and cleaned:
            found = cleaned
    return found


def _npmrc_value(home: str) -> tuple[str, str | None, str | None]:
    """Return (npmrc path, cache value or None, note or None)."""
    rc_path = os.path.join(home, ".npmrc")
    try:
        data = read_small_file(os.path.realpath(rc_path), NPMRC_MAX_BYTES)
    except FileNotFoundError:
        return rc_path, None, None
    except FsReadError as error:
        return rc_path, None, f"npmrc_unreadable: {error.reason}"
    except OSError as error:
        return rc_path, None, f"npmrc_unreadable: {error.strerror}"
    return rc_path, parse_npmrc_cache(data.decode("utf-8", errors="replace")), None


def npm_cache_location(environ: Mapping[str, str]) -> ToolPath:
    """Resolve the npm cache directory from configuration only."""
    home = environ.get("HOME")
    from_env = _environment_value(environ)
    if from_env is not None:
        name, value = from_env
        return ToolPath(_expand(value, home) if home else value, f"env:{name}", None)
    if not home:
        return ToolPath(None, "unresolved", "HOME is not set")
    rc_path, value, note = _npmrc_value(home)
    if value is not None:
        return ToolPath(_expand(value, home), f"npmrc:{rc_path}", None)
    return ToolPath(os.path.join(home, ".npm"), "default", note)
