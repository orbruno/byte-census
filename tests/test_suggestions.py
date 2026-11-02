"""Suggestion catalog, builders, ordering, and isolation (WI-SUGGESTIONS)."""

import ast
import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from byte_census import suggestions
from byte_census.model import Suggestion
from byte_census.suggestions import (
    CATALOG,
    build_artifact_suggestion,
    build_check_wide,
    build_duplicate_suggestion,
    order_suggestions,
)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "docs" / "contracts" / "examples"
SRC = ROOT / "src" / "byte_census"

EXPECTED_RISKS = {
    "docker-image-prune": "low",
    "docker-container-prune": "medium",
    "docker-system-prune-all": "high",
    "docker-volume-prune": "high",
    "uv-cache-prune": "low",
    "brew-cleanup": "low",
    "npm-cache-verify": "low",
    "artifact-remove-regenerate": "medium",
    "duplicate-remove-extra-copies": "high",
}


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}-scan.json").read_text())["data"]


def _work_item_text() -> str:
    folder = ROOT / "_Project-Management" / "Work-Items"
    names = ("DUPLICATES", "ARTIFACTS", "CACHES", "DOCKER")
    return "\n".join(next(folder.glob(f"WI-{n}__*.md")).read_text() for n in names)


def test_catalog_has_exactly_the_contract_entries_and_risks() -> None:
    assert {k: v.risk for k, v in CATALOG.items()} == EXPECTED_RISKS


def test_catalog_covers_every_command_named_in_check_work_items() -> None:
    text = _work_item_text()
    lines = [ln for ln in text.splitlines() if "suggestion" in ln.lower()]
    named = re.findall(r"`((?:docker|uv|brew|npm) [^`]+)`", "\n".join(lines))
    assert named, "work items name no commands"
    commands = {t.command for t in CATALOG.values()}
    for command in named:
        assert command in commands, command
    assert (
        "removing extra copies" in text and "duplicate-remove-extra-copies" in CATALOG
    )
    assert "artifact-remove-regenerate" in CATALOG


def test_catalog_is_immutable() -> None:
    with pytest.raises(TypeError):
        CATALOG["x"] = CATALOG["brew-cleanup"]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        CATALOG["brew-cleanup"].risk = "high"  # type: ignore[misc]


def test_suggestions_always_require_owner_authorization() -> None:
    built = build_check_wide("brew-cleanup", ["cch-1"])
    assert built.requires_owner_authorization is True
    with pytest.raises(ValueError):
        Suggestion("x", "c", "low", False, "r", requires_owner_authorization=False)
    import inspect

    for fn in (build_check_wide, build_artifact_suggestion, build_duplicate_suggestion):
        assert "requires_owner_authorization" not in inspect.signature(fn).parameters


@pytest.mark.parametrize("name", ["docker", "caches"])
def test_check_wide_entries_reproduce_examples(name: str) -> None:
    data = _example(name)
    rebuilt = [
        build_check_wide(s["id"], s["finding_ids"]).to_dict()
        for s in data["suggestions"]
    ]
    assert rebuilt == data["suggestions"]
    assert [list(d) for d in rebuilt] == [list(s) for s in data["suggestions"]]


def test_artifact_entries_reproduce_examples() -> None:
    data = _example("artifacts")
    by_id = {f["id"]: f for f in data["findings"]}
    rebuilt = []
    for s in data["suggestions"]:
        finding = by_id[s["finding_ids"][0]]
        rebuilt.append(
            build_artifact_suggestion(
                finding["id"],
                finding["target"],
                finding["details"]["project"],
                finding["details"]["regenerate_command"],
            ).to_dict()
        )
    assert rebuilt == data["suggestions"]


def test_duplicate_entries_reproduce_examples() -> None:
    data = _example("duplicates")
    finding = data["findings"][0]
    files = finding["details"]["files"]
    keep = files[0]["path"]
    remove = [files[1]["path"], *files[1]["hard_link_paths"]]
    built = build_duplicate_suggestion(finding["id"], keep, remove).to_dict()
    assert built == data["suggestions"][0]


def test_per_finding_id_is_catalog_id_at_finding_id() -> None:
    built = build_artifact_suggestion("art-1", "/p/.venv", "/p", "uv sync")
    assert built.id == "artifact-remove-regenerate@art-1"
    assert built.finding_ids == ("art-1",)


def test_quoting_escapes_single_quotes() -> None:
    built = build_artifact_suggestion("art-1", "/p/it's/node_modules", "/p/it's", "x")
    assert "'/p/it'\\''s/node_modules'" in built.command


def test_scope_and_input_validation() -> None:
    with pytest.raises(ValueError):
        build_check_wide("artifact-remove-regenerate", ["a"])
    with pytest.raises(ValueError):
        build_check_wide("brew-cleanup", [])
    with pytest.raises(KeyError):
        build_check_wide("nope", ["a"])
    with pytest.raises(ValueError):
        build_duplicate_suggestion("dup-1", "/a", [])


def test_ordering_is_risk_then_id() -> None:
    items = [
        build_check_wide("docker-volume-prune", ["d"]),
        build_check_wide("docker-image-prune", ["d"]),
        build_check_wide("docker-container-prune", ["d"]),
        build_check_wide("brew-cleanup", ["c"]),
        build_check_wide("docker-system-prune-all", ["d"]),
        build_check_wide("npm-cache-verify", ["c"]),
    ]
    ordered = order_suggestions(reversed(items))
    assert [s.id for s in ordered] == [
        "brew-cleanup",
        "docker-image-prune",
        "npm-cache-verify",
        "docker-container-prune",
        "docker-system-prune-all",
        "docker-volume-prune",
    ]


def test_examples_are_already_in_contract_order() -> None:
    for name in ("docker", "caches", "artifacts", "duplicates"):
        raw = _example(name)["suggestions"]
        built = [
            Suggestion(**{**s, "finding_ids": tuple(s["finding_ids"])}) for s in raw
        ]
        assert [s.id for s in order_suggestions(built)] == [s["id"] for s in raw]


FORBIDDEN_MODULES = {"subprocess", "os", "shutil", "byte_census.runner"}


def _imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            found.add(module)
            found |= {f"{module}.{a.name}" for a in node.names}
    return found


def test_suggestions_module_does_not_import_runner_or_process_apis() -> None:
    tree = ast.parse(Path(suggestions.__file__).read_text())
    imported = _imports(tree)
    assert not {
        i for i in imported if i.split(".")[0] in {"subprocess", "os", "shutil"}
    }
    assert not {i for i in imported if i.endswith("runner")}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"run", "Popen", "system", "execv", "spawn"}


def test_only_check_modules_call_runner_run_and_never_with_suggestions() -> None:
    """No module that touches suggestions may call `runner.run`, and no call
    to the runner passes a suggestion command or object as an argument."""
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text())
        calls_run = any(
            isinstance(n, ast.Call)
            and isinstance(n.func, (ast.Attribute, ast.Name))
            and getattr(n.func, "attr", getattr(n.func, "id", "")) == "run"
            and "runner" in ast.unparse(n.func)
            for n in ast.walk(tree)
        )
        if not calls_run:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and "runner" in ast.unparse(node.func):
                text = ast.unparse(node)
                assert "suggestion" not in text.lower(), (path.name, text)
