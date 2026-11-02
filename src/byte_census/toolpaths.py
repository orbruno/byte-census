"""Tool cache locations resolved by reading configuration, never by running a tool.

npm is not in the process allowlist: every npm invocation writes or deletes
debug logs and may create its cache directory. Its cache location is read
from, in order: the `npm_config_cache` environment variable (matched
case-insensitively, as npm does), a `cache=` line in `$HOME/.npmrc`, and the
default `$HOME/.npm`. Global and project npmrc files are not consulted.
A configured value is expanded (a leading `~`, `$HOME`, `${HOME}`) and must be
absolute afterwards; otherwise it is reported in `note` and resolution falls
through to the next source. Nothing is created, and normalization does not
touch the filesystem.
"""

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from byte_census.fsread import FsReadError, read_small_file

NPMRC_MAX_BYTES = 1024 * 1024
NPM_CACHE_KEY = "npm_config_cache"
_HOME_VARIABLE = re.compile(r"\$\{HOME\}|\$HOME(?![A-Za-z0-9_])")


@dataclass(frozen=True)
class ToolPath:
    """A resolved location and the source that decided it."""

    path: str | None
    source: str
    note: str | None


def expand_cache_value(value: str, home: str | None) -> str | None:
    """Expand `~`, `$HOME`, `${HOME}`; return a normalized absolute path or None."""
    expanded = value
    if home is not None:
        expanded = _HOME_VARIABLE.sub(lambda _: home, expanded)
        if expanded == "~" or expanded.startswith("~/"):
            expanded = home + expanded[1:]
    if not os.path.isabs(expanded):
        return None
    return os.path.normpath(expanded)


def _joined(notes: list[str]) -> str | None:
    return "; ".join(notes) if notes else None


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
    home = environ.get("HOME") or None
    notes: list[str] = []
    from_env = _environment_value(environ)
    if from_env is not None:
        name, value = from_env
        path = expand_cache_value(value, home)
        if path is not None:
            return ToolPath(path, f"env:{name}", None)
        notes.append(f"cache_not_absolute: env:{name} {value!r}")
    if home is None or not os.path.isabs(home):
        reason = "HOME is not set" if home is None else "HOME is not absolute"
        return ToolPath(None, "unresolved", _joined([*notes, reason]))
    rc_path, value, note = _npmrc_value(home)
    notes.extend([note] if note else [])
    if value is not None:
        path = expand_cache_value(value, home)
        if path is not None:
            return ToolPath(path, f"npmrc:{rc_path}", _joined(notes))
        notes.append(f"cache_not_absolute: npmrc:{rc_path} {value!r}")
    return ToolPath(os.path.join(home, ".npm"), "default", _joined(notes))
