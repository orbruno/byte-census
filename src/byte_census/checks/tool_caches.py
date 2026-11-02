"""Tool cache locations for `caches scan`: uv, npm, and Homebrew.

uv and brew report their cache directory through the runner (`uv cache dir`,
`brew --cache`). npm is never executed: its location is read from
configuration by `byte_census.toolpaths`. A tool that is missing, fails, or
points at a directory that does not exist becomes an `UnavailableSource`,
never an error. A location that would make the walk cover far more than a
cache (the filesystem root, the data-volume root, the home directory) is
refused and reported as a failed source. Nothing is created.
"""

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from byte_census import runner
from byte_census.model import CoverageEntry, UnavailableSource
from byte_census.paths import PathValidationError, validate_root
from byte_census.toolpaths import npm_cache_location

ToolRunner = Callable[[Sequence[str]], runner.RunResult]

UV_ARGV = ("uv", "cache", "dir")
BREW_ARGV = ("brew", "--cache")
SUGGESTION_IDS: Mapping[str, str] = {
    "uv": "uv-cache-prune",
    "npm": "npm-cache-verify",
    "brew": "brew-cleanup",
}


@dataclass(frozen=True)
class ToolCache:
    """A cache directory that exists, and how its location was decided."""

    tool: str
    path: str
    location_source: str
    uncertain: str | None = None


@dataclass(frozen=True)
class ToolResolution:
    """Located tool caches, unavailable sources, and subprocess accounting."""

    caches: tuple[ToolCache, ...] = ()
    unavailable: tuple[UnavailableSource, ...] = ()
    stdout_sizes: tuple[int, ...] = ()  # one entry per runner call
    coverage: tuple[CoverageEntry, ...] = ()


def default_tool_runner(argv: Sequence[str]) -> runner.RunResult:
    return runner.run(argv)


def _unavailable(tool: str, reason: str, detail: str) -> UnavailableSource:
    return UnavailableSource(tool, reason, detail)


DATA_VOLUME = "/System/Volumes/Data"


def forbidden_locations(environ: Mapping[str, str]) -> Mapping[str, str]:
    """Resolved paths a tool cache may never be, with what each one is."""
    found = {"/": "the filesystem root", DATA_VOLUME: "the data-volume root"}
    home = environ.get("HOME")
    if home and os.path.isabs(home):
        found[os.path.realpath(home)] = "the home directory"
    return found


def _check_directory(
    tool: str, raw: str, source: str, forbidden: Mapping[str, str]
) -> ToolCache | UnavailableSource:
    if not os.path.isabs(raw):
        return _unavailable(tool, "failed", f"{source} returned a relative path.")
    try:
        resolved = validate_root(raw)
    except PathValidationError as error:
        if error.reason == "not_found":
            detail = f"{raw} does not exist ({tool} cache location from {source}); "
            return _unavailable(tool, "not_installed", detail + "nothing was measured.")
        return _unavailable(tool, "failed", f"{source}: {error}")
    if str(resolved) in forbidden:
        what = forbidden[str(resolved)]
        detail = f"refusing to walk {resolved} ({source}): it is {what}, not a cache."
        return _unavailable(tool, "failed", detail)
    return ToolCache(tool, str(resolved), source)


def _ask_tool(
    tool: str, argv: tuple[str, ...], run: ToolRunner, forbidden: Mapping[str, str]
) -> tuple[ToolCache | UnavailableSource, int]:
    """Run one allowlisted command; return the outcome and its stdout size.

    A call that raised before producing output reports 0 stdout bytes.
    """
    source = " ".join(argv)
    try:
        result = run(argv)
    except runner.ExecutableNotFoundError:
        detail = f"{tool} was not found on PATH; its cache was not measured."
        return _unavailable(tool, "not_installed", detail), 0
    except runner.CommandTimeoutError as error:
        return _unavailable(tool, "timed_out", str(error)), 0
    except runner.RejectedArgvError:
        raise
    except runner.RunnerError as error:
        return _unavailable(tool, "failed", str(error)), 0
    if not result.ok:
        detail = f"`{source}` exited with status {result.returncode}."
        return _unavailable(tool, "failed", detail), result.stdout_bytes
    lines = result.stdout.strip().splitlines()
    raw = lines[0].strip() if len(lines) == 1 else ""
    if not raw:
        detail = f"`{source}` did not print exactly one path."
        return _unavailable(tool, "failed", detail), result.stdout_bytes
    return _check_directory(tool, raw, source, forbidden), result.stdout_bytes


def _uncertainty(gap: CoverageEntry) -> str:
    return (
        f"{gap.path} could not be read ({gap.reason}); the npm cache location "
        "may differ from the one reported"
    )


def _npm_cache(
    environ: Mapping[str, str], forbidden: Mapping[str, str]
) -> tuple[ToolCache | UnavailableSource, CoverageEntry | None]:
    location = npm_cache_location(environ)
    if location.path is None:
        return _unavailable("npm", "failed", f"{location.note}."), location.coverage
    outcome = _check_directory("npm", location.path, location.source, forbidden)
    gap = location.coverage
    if gap is not None and isinstance(outcome, ToolCache):
        outcome = replace(outcome, uncertain=_uncertainty(gap))
    return outcome, gap


def resolve_tool_caches(environ: Mapping[str, str], run: ToolRunner) -> ToolResolution:
    """Locate the uv, npm, and brew caches, in that order."""
    forbidden = forbidden_locations(environ)
    outcomes: list[ToolCache | UnavailableSource] = []
    sizes: list[int] = []
    gaps: list[CoverageEntry] = []
    for tool, argv in (("uv", UV_ARGV), ("npm", None), ("brew", BREW_ARGV)):
        if argv is None:
            outcome, gap = _npm_cache(environ, forbidden)
            outcomes.append(outcome)
            gaps.extend([gap] if gap else [])
            continue
        outcome, stdout_bytes = _ask_tool(tool, argv, run, forbidden)
        outcomes.append(outcome)
        sizes.append(stdout_bytes)
    return ToolResolution(
        caches=tuple(o for o in outcomes if isinstance(o, ToolCache)),
        unavailable=tuple(o for o in outcomes if isinstance(o, UnavailableSource)),
        stdout_sizes=tuple(sizes),
        coverage=tuple(gaps),
    )
