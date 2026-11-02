"""AST read-only guard for the byte_census package (WI-SAFETY AC-03).

The guard is an allowlist (policy in guard_policy.py):

- every import, including resolved relative imports, must name an allowed
  module; anything else fails;
- process access (`subprocess`, `shutil.which`, `os.killpg`) is allowed only
  in RUNNER;
- write, create, rename, delete, permission, link, timestamp, and xattr
  operations are allowed only in WRITER;
- `multiprocessing` is allowed only in MULTIPROCESSING_MODULES (empty until
  WI-PARALLEL-WALK names a traversal module);
- `eval`, `exec`, `__import__`, `vars`, `globals`, `locals`,
  `__builtins__`, introspection dunders, `sys.modules`, and `getattr`,
  `setattr`, or `delattr` with a non-constant name or through an alias are
  forbidden everywhere;
- restricted modules (os, shutil, subprocess, io, sys, ...) may not be used as
  bare values, and may not be reached through another byte_census module.

Limitation: method receivers are untyped in the AST, so write-capable Path
methods are recognized by name in any attribute position. `copy` passes only
as a call with no arguments (dict or list copy); `replace` passes only as a
call with two or more positional arguments or keywords other than `target`
(str.replace, datetime.replace); `open` passes only as a call with a constant
read mode. The guard is conservative: shadowing a restricted import name with
a local variable is reported as a bare-value use.
"""

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tests.support.guard_policy import (
    ALLOWED_IN,
    ATTR_BUILTINS,
    CONDITIONAL_ATTRIBUTES,
    FORBIDDEN,
    FORBIDDEN_BUILTINS,
    FORBIDDEN_DUNDERS,
    MODE_OPENERS,
    MODULE_ALLOWLIST,
    MULTIPROCESSING,
    OS_READ_FLAGS,
    PACKAGE_ALLOWLIST,
    PROCESS,
    RUNNER,
    VALUE_RESTRICTED,
    WATCHED_BUILTINS,
    WRITE,
    WRITE_ATTRIBUTES,
    WRITER,
    classify,
    module_allowed,
    outside,
    under,
)

__all__ = [
    "MODULE_ALLOWLIST",
    "PACKAGE_ALLOWLIST",
    "PACKAGE_DIR",
    "RUNNER",
    "WRITER",
    "Violation",
    "check_package",
    "check_source",
]

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
PACKAGE_DIR = SRC_DIR / "byte_census"


@dataclass(frozen=True)
class Violation:
    """One guard finding, rendered as file:line: reason."""

    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}"


def resolve_relative(module_path: str, level: int, name: str | None) -> str | None:
    """Resolve `from <level dots><name> import ...` for a module file path."""
    package = module_path.removesuffix(".py").split("/")[:-1]
    if level - 1 >= len(package):
        return None
    base = package[: len(package) - (level - 1)]
    return ".".join([*base, name] if name else base)


def _import_aliases(tree: ast.AST, module_path: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                aliases[alias.asname or root] = alias.name if alias.asname else root
        elif isinstance(node, ast.ImportFrom):
            source = resolve_relative(module_path, node.level, node.module)
            source = node.module if node.level == 0 else source
            for alias in node.names:
                if source is not None and alias.name != "*":
                    aliases[alias.asname or alias.name] = f"{source}.{alias.name}"
    return aliases


def _mode_reason(node: ast.expr | None, opener: str) -> str | None:
    if node is None:
        return None
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return f"{opener} mode is not a constant read mode {outside(WRITE)}"
    if set(node.value) - set("rbt"):
        return f"{opener} in mode {node.value!r} {outside(WRITE)}"
    return None


def _argument(call: ast.Call, index: int, keyword: str) -> ast.expr | None:
    for item in call.keywords:
        if item.arg == keyword:
            return item.value
    return call.args[index] if len(call.args) > index else None


def _conditional_ok(attr: str, call: ast.Call | None) -> bool:
    """Decide whether an ambiguous attribute is used in a known-safe call shape."""
    if call is None:
        return False
    keywords = {k.arg for k in call.keywords}
    if attr == "copy":
        return not call.args and not call.keywords
    if attr == "replace":
        return "target" not in keywords and len(call.args) != 1
    return True


def _writes(attr: str, call: ast.Call | None) -> bool:
    """Report whether an attribute name in this call shape is a write method."""
    if attr in WRITE_ATTRIBUTES:
        return True
    return attr in CONDITIONAL_ATTRIBUTES and not _conditional_ok(attr, call)


def _restricted_target(target: str) -> bool:
    """Report whether getattr-style access on target must be refused."""
    restricted = target in VALUE_RESTRICTED or classify(target) is not None
    return restricted or under(target, "byte_census")


class _Guard(ast.NodeVisitor):
    def __init__(self, module: str, aliases: dict[str, str]) -> None:
        self.module = module
        self.aliases = aliases
        self.found: list[Violation] = []

    def report(self, node: ast.AST, category: str, reason: str) -> None:
        if self.module not in ALLOWED_IN[category]:
            line = getattr(node, "lineno", 0)
            self.found.append(Violation(self.module, line, reason))

    def qualname(self, node: ast.expr) -> str | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        if node.id in self.aliases:
            root = self.aliases[node.id]
        elif not parts and node.id in WATCHED_BUILTINS:
            root = f"builtins.{node.id}"
        else:
            return None
        return ".".join([root, *reversed(parts)])

    def check_name(self, node: ast.AST, name: str) -> None:
        verdict = classify(name)
        if verdict is not None:
            self.report(node, *verdict)

    def check_module(self, node: ast.AST, name: str) -> None:
        if under(name, "subprocess"):
            self.report(node, PROCESS, f"import of {name} {outside(PROCESS)}")
        if module_allowed(name):
            return
        if under(name, "multiprocessing") or under(name, "concurrent"):
            self.report(node, MULTIPROCESSING, f"{name} {outside(MULTIPROCESSING)}")
        else:
            reason = f"import of {name} is not in the module allowlist"
            self.report(node, FORBIDDEN, reason)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.check_module(node, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        source = resolve_relative(self.module, node.level, node.module)
        source = node.module if node.level == 0 else source
        if source is None:
            self.report(node, FORBIDDEN, "relative import beyond the package")
            return
        self.check_module(node, source)
        for alias in node.names:
            if alias.name == "*":
                self.report(node, FORBIDDEN, f"star import from {source} is forbidden")
            elif f"{source}.{alias.name}" == "os.open":
                continue
            elif module_allowed(source):
                self.check_name(node, f"{source}.{alias.name}")

    def visit_Name(self, node: ast.Name) -> None:
        name = self.qualname(node)
        if name is None:
            return
        if name.startswith("builtins."):
            self.check_builtin_value(node)
        elif name in VALUE_RESTRICTED:
            self.report(node, FORBIDDEN, f"{name} used as a value is forbidden")
        else:
            self.check_name(node, name)

    def check_builtin_value(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_BUILTINS:
            self.report(node, FORBIDDEN, f"{node.id} is forbidden")
        elif node.id in ATTR_BUILTINS:
            self.report(node, FORBIDDEN, f"{node.id} used as a value is forbidden")
        else:
            self.report(node, WRITE, f"open used as a value {outside(WRITE)}")

    def visit_Attribute(
        self, node: ast.Attribute, call: ast.Call | None = None
    ) -> None:
        name = self.qualname(node)
        if name is None:
            self.check_attribute(node, call)
            self.generic_visit(node)
        elif name in VALUE_RESTRICTED and call is None:
            self.report(node, FORBIDDEN, f"{name} used as a value is forbidden")
        else:
            self.check_name(node, name)

    def check_attribute(self, node: ast.Attribute, call: ast.Call | None) -> None:
        attr = node.attr
        if attr in FORBIDDEN_DUNDERS:
            self.report(node, FORBIDDEN, f"{attr} access is forbidden")
        elif _writes(attr, call):
            self.report(node, WRITE, f"Path.{attr} {outside(WRITE)}")
        elif attr == "open" and call is not None:
            self.check_mode(call, _argument(call, 0, "mode"), "Path.open")

    def visit_Call(self, node: ast.Call) -> None:
        name = self.qualname(node.func)
        if name == "os.open":
            self.check_os_open(node)
        elif name in MODE_OPENERS:
            self.check_mode(node, _argument(node, MODE_OPENERS[name], "mode"), name)
        elif name is not None and name.removeprefix("builtins.") in ATTR_BUILTINS:
            self.check_attr_builtin(node, name.removeprefix("builtins."))
        elif isinstance(node.func, ast.Attribute):
            self.visit_Attribute(node.func, call=node)
        else:
            self.visit(node.func)
        self.visit_all(node.args, (k.value for k in node.keywords))

    def visit_all(self, *groups: Iterable[ast.AST]) -> None:
        for group in groups:
            for item in group:
                self.visit(item)

    def check_mode(self, node: ast.Call, mode: ast.expr | None, opener: str) -> None:
        label = "open()" if opener == "builtins.open" else f"{opener}()"
        reason = _mode_reason(mode, label)
        if reason is not None:
            self.report(node, WRITE, reason)

    def check_attr_builtin(self, node: ast.Call, builtin: str) -> None:
        if not isinstance(node.func, ast.Name) or node.func.id != builtin:
            self.report(node, FORBIDDEN, f"{builtin} through an alias is forbidden")
            return
        target = self.qualname(node.args[0]) if node.args else None
        attr = node.args[1] if len(node.args) > 1 else None
        if not isinstance(attr, ast.Constant) or not isinstance(attr.value, str):
            self.report(node, FORBIDDEN, f"{builtin} with a non-constant name")
        elif target is not None and _restricted_target(target):
            self.report(node, FORBIDDEN, f"{builtin} on {target} is forbidden")
        else:
            self.check_constant_attr(node, attr.value)

    def check_constant_attr(self, node: ast.Call, attr: str) -> None:
        if attr in FORBIDDEN_DUNDERS:
            self.report(node, FORBIDDEN, f"{attr} access is forbidden")
        elif attr in WRITE_ATTRIBUTES or attr in CONDITIONAL_ATTRIBUTES:
            self.report(node, WRITE, f"Path.{attr} {outside(WRITE)}")

    def check_os_open(self, node: ast.Call) -> None:
        flags = _argument(node, 1, "flags")
        bad = self.non_read_flags(flags) if flags is not None else ["missing"]
        if bad:
            reason = (
                f"os.open flags {', '.join(bad)} are not read-only {outside(WRITE)}"
            )
            self.report(node, WRITE, reason)

    def non_read_flags(self, node: ast.expr) -> list[str]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self.non_read_flags(node.left) + self.non_read_flags(node.right)
        name = self.qualname(node)
        if name is not None and name.startswith("os.") and name[3:] in OS_READ_FLAGS:
            return []
        return [name or ast.unparse(node)]


def check_source(source: str, module: str) -> list[Violation]:
    """Return the violations in one module's source, in line order."""
    tree = ast.parse(source, filename=module)
    guard = _Guard(module, _import_aliases(tree, module))
    guard.visit(tree)
    unique = {(v.line, v.reason): v for v in guard.found}
    return sorted(unique.values(), key=lambda v: (v.line, v.reason))


def check_package(package_dir: Path = PACKAGE_DIR) -> list[Violation]:
    """Return the violations in every module under package_dir."""
    found: list[Violation] = []
    for path in sorted(package_dir.rglob("*.py")):
        module = path.relative_to(package_dir.parent).as_posix()
        found.extend(check_source(path.read_text(encoding="utf-8"), module))
    return found
