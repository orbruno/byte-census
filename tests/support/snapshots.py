"""JSON snapshot helper with normalization of volatile fields."""

import copy
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "snapshots"
UPDATE_ENV = "BYTE_CENSUS_UPDATE_SNAPSHOTS"
ROOT_TOKEN = "<ROOT>"


def allocated_bytes_of(path: str | os.PathLike[str]) -> int:
    """Expected allocated bytes of a path, from lstat (st_blocks * 512)."""
    return os.lstat(path).st_blocks * 512


def _replace_roots(value: Any, roots: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for root in roots:
            if value.startswith(root):
                return ROOT_TOKEN + value[len(root) :]
        return value
    if isinstance(value, dict):
        return {key: _replace_roots(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_roots(item, roots) for item in value]
    return value


def _mask_meta(data: dict[str, Any]) -> None:
    meta = data.get("meta")
    if not isinstance(meta, dict):
        return
    if "captured_at" in meta:
        meta["captured_at"] = "<CAPTURED_AT>"
    if "cost" in meta:
        meta["cost"] = "<COST>"
    scope = meta.get("scope")
    if isinstance(scope, dict) and "st_dev" in scope:
        scope["st_dev"] = "<ST_DEV>"


def normalize(data: Any, roots: Iterable[str | os.PathLike[str]] = ()) -> Any:
    """Return a copy of data with volatile and machine-specific fields masked."""
    result = copy.deepcopy(data)
    if isinstance(result, dict):
        _mask_meta(result)
    ordered = sorted((str(root) for root in roots), key=len, reverse=True)
    return _replace_roots(result, tuple(ordered))


def _render(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def assert_json_snapshot(
    data: Any, name: str, roots: Iterable[str | os.PathLike[str]] = ()
) -> None:
    """Compare normalized data with tests/snapshots/<name>.json."""
    rendered = _render(normalize(data, roots))
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
