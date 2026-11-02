"""JSON snapshot helper with normalization of volatile fields.

Normalized: `meta.captured_at`, `meta.cost.elapsed_s` (the counters and
notes are kept), integer `meta.scope.st_dev` and `meta.scope.roots[].st_dev`,
fixture root prefixes in strings, and the path-derived IDs in `id`,
`finding_id`, `finding_ids`, and `suggestion_ids`. Before IDs are renumbered,
every `data.findings[].id` must equal the contract rule
`finding_id(prefix, kind, target)`. An ID `<prefix>-<12 hex>` becomes `<prefix>-<IDn>`, numbered by first
appearance, so cross-references stay checkable while hashes of machine paths
drop out. A suggestion ID `<catalog>@<finding-id>` keeps its catalog part.
Snapshots keep key order, so field order is part of the comparison.
"""

import copy
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from byte_census.model import finding_id

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "snapshots"
UPDATE_ENV = "BYTE_CENSUS_UPDATE_SNAPSHOTS"
ROOT_TOKEN = "<ROOT>"
ST_DEV_TOKEN = "<ST_DEV>"
ID_FIELDS = frozenset({"id", "finding_id", "finding_ids", "suggestion_ids"})
FINDING_ID = re.compile(r"\b([a-z]{3})-([0-9a-f]{12})\b")


def allocated_bytes_of(path: str | os.PathLike[str]) -> int:
    """Expected allocated bytes of a path, from lstat (st_blocks * 512)."""
    return os.lstat(path).st_blocks * 512


def _replace_roots(value: Any, roots: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for root in sorted(roots, key=len, reverse=True):
            value = value.replace(root, ROOT_TOKEN)
        return value
    if isinstance(value, dict):
        return {key: _replace_roots(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_roots(item, roots) for item in value]
    return value


def _mask_st_dev(holder: Any) -> None:
    if isinstance(holder, dict) and type(holder.get("st_dev")) is int:
        holder["st_dev"] = ST_DEV_TOKEN


def _mask_meta(data: dict[str, Any]) -> None:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        return
    if "captured_at" in meta:
        meta["captured_at"] = "<CAPTURED_AT>"
    cost = meta.get("cost")
    if isinstance(cost, dict) and "elapsed_s" in cost:
        cost["elapsed_s"] = "<ELAPSED_S>"
    scope = meta.get("scope")
    if not isinstance(scope, dict):
        return
    _mask_st_dev(scope)
    for root in scope.get("roots") or []:
        _mask_st_dev(root)


def _check_finding_ids(data: Any) -> None:
    body = data.get("data") if isinstance(data, dict) else None
    findings = body.get("findings") if isinstance(body, dict) else None
    for finding in findings or []:
        prefix = str(finding["id"]).split("-", 1)[0]
        expected = finding_id(prefix, finding["kind"], finding["target"])
        if finding["id"] != expected:
            raise AssertionError(
                f"finding id {finding['id']} breaks the ID rule; expected {expected}"
            )


class _IdNumbering:
    """Assigns `<IDn>` to each distinct ID hash in order of first appearance."""

    def __init__(self) -> None:
        self.numbers: dict[str, int] = {}

    def token(self, match: re.Match[str]) -> str:
        number = self.numbers.setdefault(match.group(0), len(self.numbers) + 1)
        return f"{match.group(1)}-<ID{number}>"

    def replace(self, value: Any) -> Any:
        if isinstance(value, str):
            return FINDING_ID.sub(self.token, value)
        if isinstance(value, list):
            return [self.replace(item) for item in value]
        return value

    def walk(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: self.replace(item) if key in ID_FIELDS else self.walk(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.walk(item) for item in value]
        return value


def normalize(
    data: Any,
    roots: Iterable[str | os.PathLike[str]] = (),
    volatile: Iterable[str] = (),
) -> Any:
    """Return a copy of data with volatile and machine-specific fields masked.

    `volatile` names extra dotted paths (for example
    `meta.cost.subprocess_stdout_bytes`) whose values depend on the fixture
    location; a caller that masks one must assert its exact value itself.
    """
    _check_finding_ids(data)
    result = copy.deepcopy(data)
    if isinstance(result, dict):
        _mask_meta(result)
        for dotted in volatile:
            _mask_path(result, dotted.split("."))
    ordered = sorted((str(root) for root in roots), key=len, reverse=True)
    return _IdNumbering().walk(_replace_roots(result, tuple(ordered)))


def _mask_path(holder: Any, keys: list[str]) -> None:
    for key in keys[:-1]:
        if not isinstance(holder, dict) or key not in holder:
            raise AssertionError(f"volatile path not found: {'.'.join(keys)}")
        holder = holder[key]
    if not isinstance(holder, dict) or keys[-1] not in holder:
        raise AssertionError(f"volatile path not found: {'.'.join(keys)}")
    holder[keys[-1]] = "<VOLATILE>"


def _render(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def assert_json_snapshot(
    data: Any,
    name: str,
    roots: Iterable[str | os.PathLike[str]] = (),
    volatile: Iterable[str] = (),
) -> None:
    """Compare normalized data with tests/snapshots/<name>.json."""
    rendered = _render(normalize(data, roots, volatile))
    path = SNAPSHOT_DIR / f"{name}.json"
    if os.environ.get(UPDATE_ENV) == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        return
    if not path.exists():
        raise AssertionError(
            f"Snapshot missing: {path}. Run with {UPDATE_ENV}=1 to create it."
        )
    expected = path.read_text(encoding="utf-8")
    if expected != rendered:
        raise AssertionError(
            f"Snapshot mismatch for {name}.\n--- expected\n{expected}\n--- actual\n{rendered}"
        )
