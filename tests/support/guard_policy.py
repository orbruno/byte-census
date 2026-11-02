"""Allowlist policy for the read-only AST guard (WI-SAFETY AC-03).

Every import must name a module in MODULE_ALLOWLIST or a module of a package
in PACKAGE_ALLOWLIST (the package itself). Every `module.attr` chain must name
an attribute listed for that module in ATTRIBUTE_ALLOWLISTS (or matching its
ATTRIBUTE_PREFIXES); anything else is a violation. A chain may not pass
through a module object to reach another module. `os`, `shutil`, and
`subprocess` attributes additionally carry a category that limits them to
the runner or the writer.
"""

import sys
from pathlib import Path

RUNNER = "byte_census/runner.py"
WRITER = "byte_census/legacy/report_writer.py"
FSREAD = "byte_census/fsread.py"
MULTIPROCESSING_MODULES: frozenset[str] = frozenset()

PROCESS = "process"
WRITE = "write"
FORBIDDEN = "forbidden"
MULTIPROCESSING = "multiprocessing"
READ = "read"
ENUMERATE = "enumerate"

ALLOWED_IN: dict[str, frozenset[str]] = {
    PROCESS: frozenset({RUNNER}),
    WRITE: frozenset({WRITER}),
    MULTIPROCESSING: MULTIPROCESSING_MODULES,
    READ: frozenset({FSREAD, WRITER}),
    ENUMERATE: frozenset({FSREAD}),
    FORBIDDEN: frozenset(),
}

OS_READ = frozenset(
    {"lstat", "stat", "fstat", "read", "close", "fspath", "fsencode"}
    | {"fsdecode", "environ", "getcwd", "strerror", "sep", "DirEntry"}
    | {"stat_result", "PathLike", "cpu_count", "error"}
)
OS_READ_FLAGS = frozenset(
    {"O_RDONLY", "O_NOFOLLOW", "O_NONBLOCK", "O_CLOEXEC", "O_DIRECTORY"}
)
OS_RUNNER = frozenset({"killpg"})
# Directory listing that bypasses the fsread walker's symlink, st_dev, and
# dataless checks; allowed only in FSREAD.
OS_ENUMERATE = frozenset({"scandir", "listdir", "walk", "fwalk"})
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
SHUTIL_WRITE = frozenset(
    {"copy", "copy2", "copyfile", "copyfileobj", "copymode", "copystat"}
    | {"copytree", "move", "rmtree", "chown", "make_archive", "unpack_archive"}
)
SUBPROCESS_ALLOWED = frozenset(
    {"Popen", "DEVNULL", "PIPE", "TimeoutExpired", "CalledProcessError"}
    | {"SubprocessError"}
)

ATTRIBUTE_ALLOWLISTS: dict[str, frozenset[str]] = {
    "__future__": frozenset({"annotations"}),
    "collections": frozenset(
        {"defaultdict", "Counter", "OrderedDict", "namedtuple", "deque", "ChainMap"}
    ),
    "collections.abc": frozenset(
        {"Callable", "Iterable", "Iterator", "Mapping", "Sequence", "Generator"}
        | {"MutableMapping", "Set", "Hashable", "Collection", "Container", "Sized"}
    ),
    "contextlib": frozenset(
        {"contextmanager", "suppress", "closing", "ExitStack", "nullcontext"}
    ),
    "csv": frozenset({"writer", "reader", "DictWriter", "DictReader", "QUOTE_MINIMAL"}),
    "dataclasses": frozenset(
        {"dataclass", "field", "replace", "fields", "asdict", "astuple"}
        | {"FrozenInstanceError", "is_dataclass", "InitVar"}
    ),
    "datetime": frozenset({"UTC", "datetime", "timezone", "timedelta", "date"}),
    "enum": frozenset({"Enum", "StrEnum", "IntEnum", "auto", "unique"}),
    "errno": frozenset({"errorcode"}),
    "hashlib": frozenset({"new", "sha256", "sha1", "md5", "blake2b"}),
    "io": frozenset({"StringIO", "BytesIO"}),
    "json": frozenset({"dumps", "loads", "JSONDecodeError"}),
    "os": OS_READ | OS_RUNNER | OS_WRITE | OS_ENUMERATE | {"open", "path"},
    "os.path": frozenset(
        {"isabs", "realpath", "join", "basename", "dirname", "abspath", "normpath"}
        | {"relpath", "split", "splitext", "sep", "commonpath", "isdir", "isfile"}
        | {"islink", "exists", "lexists", "getsize"}
    ),
    "pathlib": frozenset({"Path", "PurePath", "PurePosixPath", "PosixPath"}),
    "re": frozenset(
        {"compile", "match", "search", "fullmatch", "sub", "split", "findall"}
        | {"finditer", "escape", "Pattern", "Match", "IGNORECASE", "MULTILINE"}
        | {"DOTALL", "VERBOSE", "ASCII"}
    ),
    "selectors": frozenset(
        {"DefaultSelector", "EVENT_READ", "BaseSelector", "SelectorKey"}
    ),
    "shutil": frozenset({"which"}) | SHUTIL_WRITE,
    "signal": frozenset({"SIGKILL", "SIGTERM", "Signals"}),
    "stat": frozenset({"filemode"}),
    "subprocess": SUBPROCESS_ALLOWED,
    "sys": frozenset(
        {"argv", "stdout", "stderr", "exit", "platform", "version_info", "maxsize"}
    ),
    "time": frozenset({"monotonic", "monotonic_ns", "perf_counter", "time", "time_ns"}),
    "typing": frozenset(
        {"Any", "ClassVar", "Protocol", "TextIO", "TypedDict", "Final", "Literal"}
        | {"NamedTuple", "TypeAlias", "cast", "overload", "TYPE_CHECKING", "Generic"}
        | {"TypeVar", "Self", "IO", "BinaryIO", "NotRequired", "Required"}
        | {"runtime_checkable"}
    ),
    "unicodedata": frozenset({"category", "normalize", "name"}),
    "click": frozenset(
        {"command", "group", "option", "argument", "pass_context", "version_option"}
        | {"echo", "Context", "Group", "Command", "Option", "Argument", "Parameter"}
        | {"ParamType", "Choice", "IntRange", "Path"}
        | {"ClickException", "UsageError", "BadParameter", "Abort", "Exit"}
    ),
    "rich": frozenset(),
    "rich.console": frozenset({"Console"}),
    "rich.progress": frozenset({"track"}),
    "rich.table": frozenset({"Table"}),
    "rich.text": frozenset({"Text"}),
}
ATTRIBUTE_PREFIXES: dict[str, tuple[str, ...]] = {
    "errno": ("E",),
    "os": ("O_",),
    "stat": ("S_", "UF_", "SF_"),
}

MODULE_ALLOWLIST = frozenset(ATTRIBUTE_ALLOWLISTS)
PACKAGE_ALLOWLIST = ("byte_census",)

# Names that must never appear past the first attribute of a chain. A few
# stdlib module names are also ordinary method or attribute names
# (`dict.copy`, `datetime.time`), so they are not treated as modules there.
METHOD_LIKE_MODULE_NAMES = frozenset(
    {"copy", "time", "date", "select", "string", "code", "array"}
)
MODULE_NAMES = frozenset(sys.stdlib_module_names) | {"click", "rich", "byte_census"}
DEEPER_MODULE_NAMES = MODULE_NAMES - METHOD_LIKE_MODULE_NAMES

# Modules that may be used only through attribute access, never as values.
VALUE_RESTRICTED = MODULE_ALLOWLIST | {"builtins"}

FORBIDDEN_BUILTINS = frozenset(
    {"eval", "exec", "__import__", "vars", "globals", "locals", "__builtins__"}
    | {"breakpoint", "compile"}
)
ATTR_BUILTINS = frozenset({"getattr", "setattr", "delattr"})
WATCHED_BUILTINS = FORBIDDEN_BUILTINS | ATTR_BUILTINS | {"open"}

# Introspection attributes that reach globals, builtins, frames, or code
# objects. Forbidden in any attribute position and as getattr names.
FORBIDDEN_ATTRIBUTES = frozenset(
    {"__dict__", "__globals__", "__builtins__", "__subclasses__", "__class__"}
    | {"__bases__", "__mro__", "__code__", "__closure__", "__getattribute__"}
    | {"__import__", "__loader__", "__spec__", "__self__", "__func__"}
    | {"__traceback__", "__reduce__", "__reduce_ex__"}
    | {"gi_frame", "cr_frame", "ag_frame", "gi_code", "cr_code", "ag_code"}
    | {"tb_frame", "tb_next", "f_globals", "f_builtins", "f_locals", "f_back"}
    | {"f_code"}
)


def _package_modules(src_dir: Path, package: str) -> frozenset[str]:
    """Dotted names of every module and subpackage of a package under src_dir."""
    names: set[str] = set()
    for path in (src_dir / package).rglob("*.py"):
        parts = path.relative_to(src_dir).with_suffix("").parts
        names.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    return frozenset(names)


SRC_DIR = Path(__file__).resolve().parents[2] / "src"
PACKAGE_MODULES = _package_modules(SRC_DIR, "byte_census")

# Method names that write, in any attribute position (Path, os-like objects,
# rich Console). `write` is excluded: errors.py writes to a TextIO stream,
# and writable file objects are caught where they are opened.
WRITE_ATTRIBUTES = frozenset(
    {"write_text", "write_bytes", "touch", "mkdir", "rmdir", "unlink", "rename"}
    | {"chmod", "lchmod", "symlink_to", "hardlink_to", "link_to", "move"}
    | {"copy_into", "move_into", "setxattr", "removexattr", "remove"}
    | {"removedirs", "rmtree", "truncate", "ftruncate", "makedirs", "chown"}
    | {"lchown", "utime", "symlink", "mkfifo", "mknod", "copyfile", "copytree"}
    | {"copy2", "copymode", "copystat", "save_html", "save_text", "save_svg"}
)
# Content readers and directory enumerators, in any attribute position. They
# bypass fsread's FIFO, symlink, dataless, and st_dev checks.
READ_ATTRIBUTES = frozenset({"read_bytes", "read_text"})
ENUMERATE_ATTRIBUTES = frozenset({"iterdir", "glob", "rglob", "walk", "scandir"})
ENUMERATE_ATTRIBUTES = ENUMERATE_ATTRIBUTES | {"listdir"}

# Ambiguous names: safe only in the call shapes checked by the guard.
CONDITIONAL_ATTRIBUTES = frozenset({"copy", "replace", "open"})

MODE_OPENERS = {"builtins.open": 1, "pathlib.Path.open": 1}
OPENERS = frozenset({"builtins.open", "pathlib.Path.open", "os.open", "os.fdopen"})


def under(name: str, module: str) -> bool:
    return name == module or name.startswith(module + ".")


def outside(category: str) -> str:
    if category == PROCESS:
        return f"is process access outside {RUNNER}"
    if category == WRITE:
        return f"is a write operation outside {WRITER}"
    if category == READ:
        return f"is a content read outside {FSREAD} and {WRITER}"
    if category == ENUMERATE:
        return f"is directory enumeration outside {FSREAD}"
    if category == MULTIPROCESSING:
        return "is forbidden until WI-PARALLEL-WALK names a traversal module"
    return "is forbidden"


def is_module_object(name: str) -> bool:
    """Report whether a resolved name denotes a module object."""
    return name in VALUE_RESTRICTED or name in PACKAGE_MODULES


def module_allowed(name: str) -> bool:
    return name in MODULE_ALLOWLIST or any(under(name, p) for p in PACKAGE_ALLOWLIST)


def longest_module(name: str) -> str | None:
    """Return the longest allowlisted module that prefixes a dotted name."""
    parts = name.split(".")
    for size in range(len(parts), 0, -1):
        candidate = ".".join(parts[:size])
        if candidate in MODULE_ALLOWLIST:
            return candidate
    return None


def attribute_allowed(module: str, attr: str) -> bool:
    if attr in ATTRIBUTE_ALLOWLISTS[module]:
        return True
    prefixes = ATTRIBUTE_PREFIXES.get(module, ())
    return attr.startswith(prefixes) and attr.isupper() if prefixes else False


def attribute_category(attr: str) -> tuple[str, str] | None:
    """Classify a reader or enumerator method name in any attribute position."""
    if attr in READ_ATTRIBUTES:
        return READ, f"Path.{attr} {outside(READ)}"
    if attr in ENUMERATE_ATTRIBUTES:
        return ENUMERATE, f"Path.{attr} {outside(ENUMERATE)}"
    return None


def _classify_os(attr: str) -> tuple[str, str] | None:
    if attr in OS_READ or attr == "path" or attr.startswith("O_"):
        return None
    if attr == "open":
        return WRITE, "os.open referenced without a call; flags cannot be checked"
    if attr in OS_ENUMERATE:
        return ENUMERATE, f"os.{attr} {outside(ENUMERATE)}"
    if attr in OS_RUNNER:
        return PROCESS, f"os.{attr} {outside(PROCESS)}"
    if attr in OS_PROCESS or attr.startswith(OS_PROCESS_PREFIXES):
        return FORBIDDEN, f"os.{attr} {outside(FORBIDDEN)}"
    if attr in OS_WRITE:
        return WRITE, f"os.{attr} {outside(WRITE)}"
    return FORBIDDEN, f"os.{attr} is not in the os allowlist"


def _classify_category(module: str, attr: str) -> tuple[str, str] | None:
    """Apply runner and writer categories to an allowlisted attribute."""
    name = f"{module}.{attr}"
    if module == "subprocess" or name == "shutil.which":
        return PROCESS, f"{name} {outside(PROCESS)}"
    if module == "shutil":
        return WRITE, f"{name} {outside(WRITE)}"
    return None


def _classify_reexport(name: str) -> tuple[str, str] | None:
    for part in name.split(".")[1:]:
        if part in MODULE_NAMES and part != "byte_census":
            reason = f"{name} reaches {part} through byte_census; import it directly"
            return FORBIDDEN, reason
    return None


def _classify_deeper(
    module: str, name: str, deeper: list[str]
) -> tuple[str, str] | None:
    """Check attribute segments after the allowlisted one."""
    for part in deeper:
        if part in DEEPER_MODULE_NAMES:
            return FORBIDDEN, f"{name} passes through a module to reach {part}"
        if part in WRITE_ATTRIBUTES or (
            module == "pathlib" and part in {"copy", "replace"}
        ):
            return WRITE, f"Path.{part} {outside(WRITE)}"
        verdict = attribute_category(part)
        if verdict is not None:
            return verdict
    if name == "pathlib.Path.open":
        return WRITE, f"{name} referenced without a call; mode cannot be checked"
    return None


def classify(name: str) -> tuple[str, str] | None:
    """Return (category, reason) for a resolved dotted name, or None if allowed."""
    parts = name.split(".")
    dunder = next((p for p in parts if p in FORBIDDEN_ATTRIBUTES), None)
    if dunder is not None:
        return FORBIDDEN, f"{dunder} access is forbidden"
    if under(name, "byte_census"):
        return _classify_reexport(name)
    module = longest_module(name)
    if module is None:
        return FORBIDDEN, f"{name} is not in the module allowlist"
    if name == module:
        return None
    attr, *deeper = parts[len(module.split(".")) :]
    if not attribute_allowed(module, attr):
        if module == "sys" and attr == "modules":
            return FORBIDDEN, "sys.modules is forbidden"
        return FORBIDDEN, f"{module}.{attr} is not in the {module} allowlist"
    if module == "os":
        verdict = _classify_os(attr)
        if verdict is not None:
            return verdict
    else:
        verdict = _classify_category(module, attr)
        if verdict is not None:
            return verdict
    return _classify_deeper(module, name, deeper)
