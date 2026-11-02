"""AST read-only guard for the byte_census package (WI-SAFETY AC-03).

The guard is an allowlist. It resolves import aliases and classifies every
dotted name, builtin `open`, `os.open` flag set, and Path-style method call:

- process access (`subprocess`, `shutil.which`) is allowed only in RUNNER;
- write, create, rename, delete, permission, link, timestamp, and xattr
  operations are allowed only in WRITER;
- `multiprocessing` and process pools are allowed only in
  MULTIPROCESSING_MODULES (empty until WI-PARALLEL-WALK names one);
- `ctypes`, `pty`, `tempfile`, `importlib`, raw `posix`, `os.fork`,
  `os.posix_spawn`, other process functions, `eval`, `exec`, `__import__`,
  dynamic `getattr` on a restricted module, and any `os` function outside
  OS_READ are forbidden everywhere.

Limitation: receivers of method calls are untyped in the AST, so Path write
methods are recognized by name. `.replace` counts as `Path.replace` only with
exactly one positional argument, because `str.replace` needs two.
"""

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
PACKAGE_DIR = SRC_DIR / "byte_census"
RUNNER = "byte_census/runner.py"
WRITER = "byte_census/legacy/report_writer.py"
MULTIPROCESSING_MODULES: frozenset[str] = frozenset()

PROCESS = "process"
WRITE = "write"
FORBIDDEN = "forbidden"
MULTIPROCESSING = "multiprocessing"

ALLOWED_IN: dict[str, frozenset[str]] = {
    PROCESS: frozenset({RUNNER}),
    WRITE: frozenset({WRITER}),
    MULTIPROCESSING: MULTIPROCESSING_MODULES,
    FORBIDDEN: frozenset(),
}

FORBIDDEN_MODULES = (
    "ctypes",
    "_ctypes",
    "pty",
    "tempfile",
    "importlib",
    "posix",
    "nt",
    "_posixsubprocess",
)
FORBIDDEN_BUILTINS = frozenset({"eval", "exec", "__import__"})
RESTRICTED_MODULES = frozenset(
    {"os", "os.path", "shutil", "subprocess", "io", "pathlib", "posix"}
)

OS_READ = frozenset(
    {
        "lstat",
        "stat",
        "fstat",
        "scandir",
        "read",
        "close",
        "fspath",
        "fsencode",
        "fsdecode",
        "path",
        "environ",
        "getcwd",
        "strerror",
        "sep",
        "DirEntry",
        "stat_result",
        "PathLike",
        "cpu_count",
        "error",
    }
)
OS_READ_FLAGS = frozenset(
    {"O_RDONLY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC", "O_DIRECTORY"}
)
OS_PROCESS = frozenset(
    {"fork", "forkpty", "posix_spawn", "posix_spawnp", "system", "popen"}
    | {"kill", "killpg", "abort"}
)
OS_PROCESS_PREFIXES = ("exec", "spawn")
OS_WRITE = frozenset(
    {"remove", "unlink", "rename", "renames", "replace", "rmdir", "removedirs"}
    | {"mkdir", "makedirs", "mkfifo", "mknod", "link", "symlink"}
    | {"chmod", "lchmod", "fchmod", "chown", "lchown", "fchown", "chflags", "lchflags"}
    | {"utime", "truncate", "ftruncate", "write", "pwrite", "writev", "pwritev"}
    | {"sendfile", "copy_file_range", "setxattr", "removexattr"}
)
PATH_WRITE_METHODS = frozenset(
    {"write_text", "write_bytes", "touch", "mkdir", "rmdir", "unlink", "rename"}
    | {"chmod", "lchmod", "symlink_to", "hardlink_to", "link_to"}
    | {"setxattr", "removexattr"}
)
MODE_OPENERS = {"builtins.open": 1, "io.open": 1, "io.FileIO": 1, "codecs.open": 1}


@dataclass(frozen=True)
class Violation:
    """One guard finding, rendered as file:line: reason."""

    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}"


def _under(name: str, module: str) -> bool:
    return name == module or name.startswith(module + ".")


def _outside(category: str) -> str:
    if category == PROCESS:
        return f"is process access outside {RUNNER}"
    if category == WRITE:
        return f"is a write operation outside {WRITER}"
    if category == MULTIPROCESSING:
        return "is forbidden until WI-PARALLEL-WALK names a traversal module"
    return "is forbidden"


def _classify_os(name: str) -> tuple[str, str] | None:
    attr = name.split(".")[1]
    if attr in OS_READ or attr.startswith("O_"):
        return None
    if attr == "open":
        return WRITE, "os.open referenced without a call; flags cannot be checked"
    if attr in OS_PROCESS or attr.startswith(OS_PROCESS_PREFIXES):
        return FORBIDDEN, f"os.{attr} {_outside(FORBIDDEN)}"
    if attr in OS_WRITE:
        return WRITE, f"os.{attr} {_outside(WRITE)}"
    return FORBIDDEN, f"os.{attr} is not in the os allowlist"


def classify(name: str) -> tuple[str, str] | None:
    """Return (category, reason) for a resolved dotted name, or None if allowed."""
    if any(_under(name, module) for module in FORBIDDEN_MODULES):
        return FORBIDDEN, f"{name} {_outside(FORBIDDEN)}"
    if _under(name, "multiprocessing") or _under(name, "concurrent.futures.process"):
        return MULTIPROCESSING, f"{name} {_outside(MULTIPROCESSING)}"
    if name == "concurrent.futures.ProcessPoolExecutor":
        return MULTIPROCESSING, f"{name} {_outside(MULTIPROCESSING)}"
    if _under(name, "subprocess") or name == "shutil.which":
        return PROCESS, f"{name} {_outside(PROCESS)}"
    if _under(name, "shutil") and name != "shutil":
        return WRITE, f"{name} {_outside(WRITE)}"
    if _under(name, "xattr"):
        return WRITE, f"{name} {_outside(WRITE)}"
    if _under(name, "os.path") or name == "os":
        return None
    if _under(name, "os"):
        return _classify_os(name)
    if _under(name, "pathlib") and name.rsplit(".", 1)[-1] in PATH_WRITE_METHODS:
        return WRITE, f"{name} {_outside(WRITE)}"
    return None


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
                else:
                    root = alias.name.split(".")[0]
                    aliases[root] = root
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _mode_reason(node: ast.expr | None, opener: str) -> str | None:
    if node is None:
        return None
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return f"{opener} mode is not a constant read mode {_outside(WRITE)}"
    if set(node.value) - set("rbt"):
        return f"{opener} in mode {node.value!r} {_outside(WRITE)}"
    return None


def _argument(call: ast.Call, index: int, keyword: str) -> ast.expr | None:
    for item in call.keywords:
        if item.arg == keyword:
            return item.value
    return call.args[index] if len(call.args) > index else None


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
        elif not parts and node.id in ("open", "getattr", *FORBIDDEN_BUILTINS):
            root = f"builtins.{node.id}"
        else:
            return None
        return ".".join([root, *reversed(parts)])

    def check_name(self, node: ast.AST, name: str) -> None:
        verdict = classify(name)
        if verdict is not None:
            self.report(node, *verdict)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.check_name(node, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not node.module or node.level:
            return
        for alias in node.names:
            if alias.name == "*":
                if any(_under(node.module, m) for m in RESTRICTED_MODULES):
                    self.report(
                        node, FORBIDDEN, f"star import from {node.module} is forbidden"
                    )
                continue
            if f"{node.module}.{alias.name}" != "os.open":
                self.check_name(node, f"{node.module}.{alias.name}")
            else:
                self.check_name(node, node.module)

    def visit_Name(self, node: ast.Name) -> None:
        name = self.qualname(node)
        if name is None:
            return
        if name.startswith("builtins."):
            if node.id in FORBIDDEN_BUILTINS:
                self.report(node, FORBIDDEN, f"{node.id}() is forbidden")
            return
        self.check_name(node, name)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        name = self.qualname(node)
        if name is None:
            self.generic_visit(node)
        else:
            self.check_name(node, name)

    def visit_Call(self, node: ast.Call) -> None:
        name = self.qualname(node.func)
        if name == "os.open":
            self.check_os_open(node)
            self.visit_all(node.args, (k.value for k in node.keywords))
            return
        if name in MODE_OPENERS:
            self.check_mode(node, _argument(node, MODE_OPENERS[name], "mode"), name)
        elif name == "builtins.getattr":
            self.check_getattr(node)
        elif name is None and isinstance(node.func, ast.Attribute):
            self.check_method(node, node.func.attr)
        self.generic_visit(node)

    def visit_all(self, *groups: Iterable[ast.AST]) -> None:
        for group in groups:
            for item in group:
                self.visit(item)

    def check_mode(self, node: ast.Call, mode: ast.expr | None, opener: str) -> None:
        label = "open()" if opener == "builtins.open" else f"{opener}()"
        reason = _mode_reason(mode, label)
        if reason is not None:
            self.report(node, WRITE, reason)

    def check_method(self, node: ast.Call, attr: str) -> None:
        if attr == "open":
            self.check_mode(node, _argument(node, 0, "mode"), "Path.open")
        elif attr in PATH_WRITE_METHODS:
            self.report(node, WRITE, f"Path.{attr} {_outside(WRITE)}")
        elif attr == "replace" and len(node.args) == 1 and not node.keywords:
            self.report(node, WRITE, f"Path.replace {_outside(WRITE)}")

    def check_getattr(self, node: ast.Call) -> None:
        target = self.qualname(node.args[0]) if node.args else None
        if target in RESTRICTED_MODULES:
            self.report(node, FORBIDDEN, f"dynamic getattr on {target} is forbidden")

    def check_os_open(self, node: ast.Call) -> None:
        flags = _argument(node, 1, "flags")
        bad = self.non_read_flags(flags) if flags is not None else ["missing"]
        if bad:
            reason = (
                f"os.open flags {', '.join(bad)} are not read-only {_outside(WRITE)}"
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
    guard = _Guard(module, _import_aliases(tree))
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
