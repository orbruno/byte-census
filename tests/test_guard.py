"""AST read-only guard (WI-SAFETY AC-03, DOD-04).

The guard itself lives in tests/support/read_only_guard.py. These tests
prove it catches planted violations in synthetic sources and that the real
package passes.
"""

import textwrap
from pathlib import Path

import pytest

from tests.support.read_only_guard import (
    PACKAGE_DIR,
    RUNNER,
    WRITER,
    Violation,
    check_package,
    check_source,
)

PLAIN = "byte_census/scan_module.py"


def violations(source: str, module: str = PLAIN) -> list[Violation]:
    return check_source(textwrap.dedent(source), module)


def assert_flags(source: str, fragment: str, module: str = PLAIN) -> None:
    found = violations(source, module)
    assert found, f"guard missed: {source!r}"
    assert any(fragment in v.reason for v in found), [str(v) for v in found]


def test_real_package_passes() -> None:
    found = check_package(PACKAGE_DIR)

    assert found == [], "\n".join(str(v) for v in found)


def test_guard_scans_package_not_tests() -> None:
    assert PACKAGE_DIR.name == "byte_census"
    assert PACKAGE_DIR.parent.name == "src"


def test_violation_renders_file_line_reason() -> None:
    (found,) = violations("import os\n\nos.remove('x')\n")

    assert str(found) == f"{PLAIN}:3: os.remove is a write operation outside {WRITER}"


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\n",
        "import subprocess as sp\n",
        "from subprocess import run\n",
        "from subprocess import run as go\ngo(['ls'])\n",
        "import shutil\nshutil.which('docker')\n",
        "from shutil import which\n",
        "from shutil import which as w\nw('x')\n",
    ],
)
def test_process_access_outside_runner_is_flagged(source: str) -> None:
    assert_flags(source, "process")


@pytest.mark.parametrize(
    "source",
    [
        "import subprocess\nsubprocess.run(['x'], shell=False, timeout=1)\n",
        "import shutil\nshutil.which('docker')\n",
        "from shutil import which\nwhich('uv')\n",
    ],
)
def test_runner_may_use_subprocess_and_which(source: str) -> None:
    assert violations(source, RUNNER) == []


def test_runner_may_not_use_other_shutil_functions() -> None:
    assert_flags("import shutil\nshutil.rmtree('/x')\n", "write", RUNNER)


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("import os\nos.remove('x')\n", "os.remove"),
        ("import os as o\no.unlink('x')\n", "os.unlink"),
        ("from os import rename\nrename('a', 'b')\n", "os.rename"),
        ("from os import replace as swap\nswap('a', 'b')\n", "os.replace"),
        ("import os\nos.mkdir('d')\n", "os.mkdir"),
        ("import os\nos.makedirs('d')\n", "os.makedirs"),
        ("import os\nos.rmdir('d')\n", "os.rmdir"),
        ("import os\nos.chmod('x', 0o777)\n", "os.chmod"),
        ("import os\nos.chown('x', 0, 0)\n", "os.chown"),
        ("import os\nos.link('a', 'b')\n", "os.link"),
        ("import os\nos.symlink('a', 'b')\n", "os.symlink"),
        ("import os\nos.utime('x')\n", "os.utime"),
        ("import os\nos.write(1, b'x')\n", "os.write"),
        ("import os\nos.fdopen(3, 'w')\n", "os.fdopen"),
        ("import os\nos.truncate('x', 0)\n", "os.truncate"),
        ("import os\nos.setxattr('x', 'k', b'v')\n", "os.setxattr"),
        ("import os\nos.removexattr('x', 'k')\n", "os.removexattr"),
        ("import os\nos.chflags('x', 0)\n", "os.chflags"),
        ("import os\nos.mkfifo('x')\n", "os.mkfifo"),
        ("import os\nf = os.remove\n", "os.remove"),
        ("import shutil\nshutil.copy('a', 'b')\n", "shutil.copy"),
        ("import shutil\nshutil.copyfile('a', 'b')\n", "shutil.copyfile"),
        ("import shutil\nshutil.copytree('a', 'b')\n", "shutil.copytree"),
        ("import shutil\nshutil.move('a', 'b')\n", "shutil.move"),
        ("import shutil\nshutil.rmtree('a')\n", "shutil.rmtree"),
        ("import xattr\n", "xattr"),
    ],
)
def test_write_functions_outside_writer_are_flagged(source: str, fragment: str) -> None:
    assert_flags(source, fragment)
    assert_flags(source, "write")


@pytest.mark.parametrize(
    "method",
    [
        "write_text('x')",
        "write_bytes(b'x')",
        "touch()",
        "mkdir()",
        "rmdir()",
        "unlink()",
        "rename('b')",
        "replace('b')",
        "chmod(0o777)",
        "lchmod(0o777)",
        "symlink_to('b')",
        "hardlink_to('b')",
    ],
)
def test_path_write_methods_are_flagged(method: str) -> None:
    source = f"from pathlib import Path\nPath('a').{method}\n"

    assert_flags(source, "write")


def test_str_replace_is_not_a_path_replace() -> None:
    assert violations("name = 'a'.replace('a', 'b')\n") == []


@pytest.mark.parametrize(
    "source",
    [
        "open('x', 'w')\n",
        "open('x', 'a')\n",
        "open('x', 'r+')\n",
        "open('x', 'xb')\n",
        "open('x', mode='wb')\n",
        "open('x', buffering=1, mode='a')\n",
        "mode = 'r'\nopen('x', mode)\n",
        "import io\nio.open('x', 'w')\n",
        "from pathlib import Path\nPath('x').open('w')\n",
        "from pathlib import Path\nPath('x').open(mode='a')\n",
        "from pathlib import Path\nPath('x').open('r+b')\n",
    ],
)
def test_open_in_write_mode_is_flagged(source: str) -> None:
    assert_flags(source, "open")


@pytest.mark.parametrize(
    "source",
    [
        "open('x')\n",
        "open('x', 'rb')\n",
        "open('x', mode='r')\n",
        "from pathlib import Path\nPath('x').open()\n",
        "from pathlib import Path\nPath('x').open('rb')\n",
    ],
)
def test_open_for_reading_is_allowed(source: str) -> None:
    assert violations(source) == []


@pytest.mark.parametrize(
    "flags",
    [
        "os.O_WRONLY",
        "os.O_RDWR",
        "os.O_RDONLY | os.O_CREAT",
        "os.O_RDONLY | os.O_TRUNC",
        "os.O_APPEND",
        "os.O_RDONLY | os.O_EXCL",
        "flags",
        "os.O_RDONLY + 1",
    ],
)
def test_os_open_with_write_or_unknown_flags_is_flagged(flags: str) -> None:
    source = f"import os\nflags = 0\nos.open('x', {flags})\n"

    assert_flags(source, "os.open")


def test_os_open_read_flags_are_allowed() -> None:
    source = "import os\nos.open('x', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)\n"

    assert violations(source) == []


def test_os_open_keyword_flags_are_checked() -> None:
    assert_flags("import os\nos.open('x', flags=os.O_WRONLY)\n", "os.open")


def test_from_os_import_open_is_checked() -> None:
    assert_flags("from os import open as o, O_CREAT\no('x', O_CREAT)\n", "os.open")


@pytest.mark.parametrize(
    "source",
    [
        "import ctypes\n",
        "from ctypes import CDLL\n",
        "import pty\n",
        "import tempfile\n",
        "from tempfile import mkstemp\n",
        "import multiprocessing\n",
        "from multiprocessing import Pool\n",
        "import multiprocessing.pool\n",
        "from concurrent.futures import ProcessPoolExecutor\n",
        "import concurrent.futures as cf\ncf.ProcessPoolExecutor()\n",
        "import os\nos.fork()\n",
        "import os\nos.posix_spawn('x', [], {})\n",
        "import os\nos.posix_spawnp('x', [], {})\n",
        "import os\nos.system('ls')\n",
        "import os\nos.popen('ls')\n",
        "import os\nos.execv('x', [])\n",
        "import os\nos.kill(1, 9)\n",
        "import os\ngetattr(os, 'remove')('x')\n",
        "import os as o\ngetattr(o, name)\n",
        "import shutil\ngetattr(shutil, 'rmtree')\n",
        "from os import *\n",
        "__import__('os')\n",
        "import importlib\n",
        "eval('1')\n",
        "exec('x = 1')\n",
        "import posix\n",
        "import _posixsubprocess\n",
    ],
)
def test_forbidden_everywhere(source: str) -> None:
    for module in (PLAIN, RUNNER, WRITER):
        assert violations(source, module), (module, source)


def test_unlisted_os_function_is_flagged() -> None:
    assert_flags("import os\nos.getlogin()\n", "not in the os allowlist")


@pytest.mark.parametrize(
    "source",
    [
        "import os\nos.lstat('x')\n",
        "import os\nos.fstat(3)\n",
        "import os\nos.scandir('.')\n",
        "import os\nos.read(3, 10)\n",
        "import os\nos.close(3)\n",
        "import os\nos.path.join('a', 'b')\n",
        "import os.path\nos.path.realpath('a')\n",
        "from os import path\npath.isdir('a')\n",
        "from os.path import join\njoin('a', 'b')\n",
        "import os\nenv = dict(os.environ)\n",
        "import os\nos.fsencode('a')\n",
        "import os\nx: os.DirEntry[str]\n",
        "import os\nx: os.stat_result\n",
    ],
)
def test_read_only_os_use_is_allowed(source: str) -> None:
    assert violations(source) == []


def test_writer_may_write() -> None:
    source = """
        import os
        import shutil
        from pathlib import Path
        Path('x').write_text('y')
        os.replace('a', 'b')
        shutil.copy('a', 'b')
        open('x', 'w')
        os.open('x', os.O_WRONLY | os.O_CREAT)
    """

    assert violations(source, WRITER) == []


def test_writer_may_not_run_processes() -> None:
    assert_flags("import subprocess\n", "process", WRITER)


def test_runner_may_not_write() -> None:
    assert_flags("from pathlib import Path\nPath('x').unlink()\n", "write", RUNNER)


def test_shadowed_name_is_not_resolved_to_os() -> None:
    source = "import os\ndef f(os):\n    return os\n"

    assert violations(source) == []


def test_check_package_reports_relative_paths(tmp_path: Path) -> None:
    package = tmp_path / "byte_census"
    (package / "legacy").mkdir(parents=True)
    (package / "ok.py").write_text("import os\nos.lstat('x')\n")
    (package / "legacy" / "bad.py").write_text("import tempfile\n")

    (found,) = check_package(package)

    assert found.path == "byte_census/legacy/bad.py"
    assert found.line == 1
