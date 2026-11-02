"""Allowlist policy for the read-only AST guard (WI-SAFETY AC-03).

Every import must name a module in MODULE_ALLOWLIST or a package in
PACKAGE_ALLOWLIST. Within the allowed modules, `classify` maps each resolved
dotted name to a category and reason, or to None when it is permitted.
"""

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

MODULE_ALLOWLIST = frozenset(
    {"__future__", "collections", "collections.abc", "contextlib", "csv"}
    | {"dataclasses", "datetime", "enum", "errno", "hashlib", "io", "json"}
    | {"os", "os.path", "pathlib", "re", "selectors", "shutil", "signal"}
    | {"stat", "subprocess", "sys", "time", "typing", "unicodedata"}
)
PACKAGE_ALLOWLIST = ("byte_census", "click", "rich")

# Modules that may be used only through attribute access, never as values.
VALUE_RESTRICTED = frozenset(
    {"os", "os.path", "shutil", "subprocess", "io", "sys", "signal", "selectors"}
    | {"pathlib", "builtins"}
)
REEXPORT_RESTRICTED = frozenset(
    {"os", "shutil", "subprocess", "io", "sys", "signal", "selectors", "pathlib"}
    | {"builtins"}
)

FORBIDDEN_BUILTINS = frozenset(
    {"eval", "exec", "__import__", "vars", "globals", "locals", "__builtins__"}
    | {"breakpoint"}
)
ATTR_BUILTINS = frozenset({"getattr", "setattr", "delattr"})
WATCHED_BUILTINS = FORBIDDEN_BUILTINS | ATTR_BUILTINS | {"open"}

FORBIDDEN_DUNDERS = frozenset(
    {"__dict__", "__globals__", "__builtins__", "__subclasses__", "__class__"}
    | {"__bases__", "__mro__", "__code__", "__closure__", "__getattribute__"}
    | {"__import__", "__loader__", "__spec__", "__self__", "__func__"}
)

OS_READ = frozenset(
    {"lstat", "stat", "fstat", "scandir", "read", "close", "fspath", "fsencode"}
    | {"fsdecode", "path", "environ", "getcwd", "strerror", "sep", "DirEntry"}
    | {"stat_result", "PathLike", "cpu_count", "error"}
)
OS_READ_FLAGS = frozenset(
    {"O_RDONLY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC", "O_DIRECTORY"}
)
OS_RUNNER = frozenset({"killpg"})
OS_PROCESS = frozenset(
    {"fork", "forkpty", "posix_spawn", "posix_spawnp", "system", "popen"}
    | {"kill", "abort"}
)
OS_PROCESS_PREFIXES = ("exec", "spawn")
OS_WRITE = frozenset(
    {"remove", "unlink", "rename", "renames", "replace", "rmdir", "removedirs"}
    | {"mkdir", "makedirs", "mkfifo", "mknod", "link", "symlink", "fdopen"}
    | {"chmod", "lchmod", "fchmod", "chown", "lchown", "fchown", "chflags", "lchflags"}
    | {"utime", "truncate", "ftruncate", "write", "pwrite", "writev", "pwritev"}
    | {"sendfile", "copy_file_range", "setxattr", "removexattr"}
)

ATTRIBUTE_ALLOWLISTS: dict[str, frozenset[str]] = {
    "io": frozenset({"StringIO", "BytesIO"}),
    "sys": frozenset(
        {"argv", "stdout", "stderr", "exit", "platform", "version_info", "maxsize"}
    ),
    "signal": frozenset({"SIGKILL", "SIGTERM", "Signals"}),
    "selectors": frozenset(
        {"DefaultSelector", "EVENT_READ", "BaseSelector", "SelectorKey"}
    ),
}

# Method names that write, in any attribute position (Path, rich Console).
WRITE_ATTRIBUTES = frozenset(
    {"write_text", "write_bytes", "touch", "mkdir", "rmdir", "unlink", "rename"}
    | {"chmod", "lchmod", "symlink_to", "hardlink_to", "link_to", "move"}
    | {"copy_into", "move_into", "setxattr", "removexattr"}
    | {"save_html", "save_text", "save_svg"}
)
# Ambiguous names: safe only in the call shapes checked by the guard.
CONDITIONAL_ATTRIBUTES = frozenset({"copy", "replace", "open"})

MODE_OPENERS = {
    "builtins.open": 1,
    "io.open": 1,
    "io.FileIO": 1,
    "pathlib.Path.open": 1,
}
CLICK_FORBIDDEN = {
    "click.launch": FORBIDDEN,
    "click.edit": FORBIDDEN,
    "click.open_file": WRITE,
    "click.File": WRITE,
}


def under(name: str, module: str) -> bool:
    return name == module or name.startswith(module + ".")


def outside(category: str) -> str:
    if category == PROCESS:
        return f"is process access outside {RUNNER}"
    if category == WRITE:
        return f"is a write operation outside {WRITER}"
    if category == MULTIPROCESSING:
        return "is forbidden until WI-PARALLEL-WALK names a traversal module"
    return "is forbidden"


def module_allowed(name: str) -> bool:
    return name in MODULE_ALLOWLIST or any(under(name, p) for p in PACKAGE_ALLOWLIST)


def _classify_os(name: str) -> tuple[str, str] | None:
    attr = name.split(".")[1]
    if attr in OS_READ or attr.startswith("O_"):
        return None
    if attr == "open":
        return WRITE, "os.open referenced without a call; flags cannot be checked"
    if attr in OS_RUNNER:
        return PROCESS, f"os.{attr} {outside(PROCESS)}"
    if attr in OS_PROCESS or attr.startswith(OS_PROCESS_PREFIXES):
        return FORBIDDEN, f"os.{attr} {outside(FORBIDDEN)}"
    if attr in OS_WRITE:
        return WRITE, f"os.{attr} {outside(WRITE)}"
    return FORBIDDEN, f"os.{attr} is not in the os allowlist"


def _classify_reexport(name: str) -> tuple[str, str] | None:
    parts = name.split(".")
    for part in parts[1:]:
        if part in REEXPORT_RESTRICTED:
            reason = f"{name} reaches {part} through byte_census; import it directly"
            return FORBIDDEN, reason
    return None


def _classify_attribute_allowlist(name: str) -> tuple[str, str] | None:
    module, _, rest = name.partition(".")
    attr = rest.split(".")[0]
    if name in MODE_OPENERS:
        return WRITE, f"{name} referenced without a call; mode cannot be checked"
    if attr in ATTRIBUTE_ALLOWLISTS[module]:
        return None
    if module == "sys" and attr == "modules":
        return FORBIDDEN, "sys.modules is forbidden"
    return FORBIDDEN, f"{module}.{attr} is not in the {module} allowlist"


def _classify_restricted(name: str) -> tuple[str, str] | None:
    """Classify names under subprocess, shutil, os, and attribute allowlists."""
    if under(name, "subprocess") or name == "shutil.which":
        return PROCESS, f"{name} {outside(PROCESS)}"
    if under(name, "shutil"):
        return WRITE, f"{name} {outside(WRITE)}"
    if under(name, "os.path"):
        return None
    if under(name, "os"):
        return _classify_os(name)
    module = name.split(".")[0]
    if module in ATTRIBUTE_ALLOWLISTS:
        return _classify_attribute_allowlist(name)
    return None


def classify(name: str) -> tuple[str, str] | None:
    """Return (category, reason) for a resolved dotted name, or None if allowed."""
    parts = name.split(".")
    dunder = next((p for p in parts if p in FORBIDDEN_DUNDERS), None)
    if dunder is not None:
        return FORBIDDEN, f"{dunder} access is forbidden"
    if name in VALUE_RESTRICTED:
        return None
    if under(name, "byte_census"):
        return _classify_reexport(name)
    if name in CLICK_FORBIDDEN:
        category = CLICK_FORBIDDEN[name]
        return category, f"{name} {outside(category)}"
    if under(name, "pathlib") and parts[-1] in WRITE_ATTRIBUTES | {"copy", "replace"}:
        return WRITE, f"Path.{parts[-1]} {outside(WRITE)}"
    if name == "pathlib.Path.open":
        return WRITE, f"{name} referenced without a call; mode cannot be checked"
    return _classify_restricted(name)
