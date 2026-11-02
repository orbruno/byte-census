"""AST read-only guard (WI-SAFETY AC-03, DOD-04).

The guard itself lives in tests/support/read_only_guard.py. These tests
prove it catches planted violations in synthetic sources and that the real
package passes.
"""

import textwrap
from pathlib import Path

import pytest

from tests.support.read_only_guard import (
    ATTRIBUTE_ALLOWLISTS,
    FSREAD,
    MODULE_ALLOWLIST,
    PACKAGE_ALLOWLIST,
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
        "import subprocess\nsubprocess.Popen(['x'], shell=False)\n",
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
def test_open_for_reading_is_allowed_in_fsread(source: str) -> None:
    assert violations(source, FSREAD) == []


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

    assert violations(source, FSREAD) == []


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


def test_shadowing_a_restricted_alias_is_flagged_conservatively() -> None:
    source = "import os\ndef f(os):\n    return os\n"

    assert_flags(source, "used as a value")


def test_check_package_reports_relative_paths(tmp_path: Path) -> None:
    package = tmp_path / "byte_census"
    (package / "legacy").mkdir(parents=True)
    (package / "ok.py").write_text("import os\nos.lstat('x')\n")
    (package / "legacy" / "bad.py").write_text("import tempfile\n")

    (found,) = check_package(package)

    assert found.path == "byte_census/legacy/bad.py"
    assert found.line == 1


# M1: confirmed bypasses from the security review, each planted.

BYPASSES = [
    ("import os\nf = os\nf.remove('x')\n", "used as a value"),
    ("import os\ng = getattr\ng(os, 'remove')('x')\n", "getattr"),
    ("__builtins__['open']('x', 'w')\n", "__builtins__"),
    ("import sys\nsys.modules['os'].remove('x')\n", "sys.modules"),
    ("import os\nvars(os)['remove']('x')\n", "vars"),
    ("globals()['x'] = 1\n", "globals"),
    ("locals()\n", "locals"),
    ("from pathlib import Path\nw = Path('x').write_text\nw('y')\n", "write_text"),
    ("getattr(obj, 'write_text')('y')\n", "write_text"),
    ("getattr(obj, name)\n", "non-constant"),
    ("setattr(obj, name, 1)\n", "non-constant"),
    ("import os\nsetattr(os, 'remove', print)\n", "setattr on os"),
    ("delattr(obj, name)\n", "non-constant"),
    ("getattr(obj, '__dict__')\n", "__dict__"),
    ("x = obj.__dict__\n", "__dict__"),
    ("x = f.__globals__['os']\n", "__globals__"),
    ("from pathlib import Path\nPath('a').replace(target='b')\n", "Path.replace"),
    ("from pathlib import Path\nPath.replace(p, 'b')\n", "Path.replace"),
    ("from pathlib import Path\nPath('a').copy('b')\n", "Path.copy"),
    ("from pathlib import Path\nPath('a').copy(target='b')\n", "Path.copy"),
    ("from pathlib import Path\nPath('a').move('b')\n", "Path.move"),
    ("from pathlib import Path\nPath('a').copy_into('d')\n", "Path.copy_into"),
    ("from pathlib import Path\nPath('a').move_into('d')\n", "Path.move_into"),
    ("from pathlib import Path\nPath.open(p, 'w')\n", "open"),
    ("o = open\no('x', 'w')\n", "open used as a value"),
    ("from . import fsread\nfsread.os.remove('x')\n", "through byte_census"),
    ("from .fsread import os\n", "through byte_census"),
    ("from byte_census import fsread\nfsread.os.remove('x')\n", "through byte_census"),
    ("import byte_census.runner\nbyte_census.runner.subprocess.run([])\n", "through"),
    ("from .. import x\n", "relative import"),
    ("import _io\n", "_io"),
    ("import gzip\n", "gzip"),
    ("import zipfile\n", "zipfile"),
    ("import sqlite3\n", "sqlite3"),
    ("import logging\n", "logging"),
    ("from logging import FileHandler\n", "logging"),
    ("import shelve\n", "shelve"),
    ("import mmap\n", "mmap"),
    ("import fcntl\n", "fcntl"),
    ("import asyncio\n", "asyncio"),
    ("import platform\nplatform.popen('ls')\n", "platform"),
    ("import webbrowser\n", "webbrowser"),
    ("import xattr\n", "xattr"),
    ("import builtins\n", "builtins"),
    ("import io\nio.FileIO('x', 'w')\n", "io.FileIO"),
    ("import io\nf = io.open\n", "io.open"),
    ("import io\nio.open_code('x')\n", "io allowlist"),
    ("import sys\nsys._getframe()\n", "sys allowlist"),
    ("import signal\nsignal.signal(2, print)\n", "signal allowlist"),
    ("import click\nclick.launch('x')\n", "click.launch"),
    ("import click\nclick.open_file('x', 'w')\n", "click.open_file"),
    ("console.save_html('x.html')\n", "save_html"),
    ("import shutil\nw = shutil.which\n", "process"),
    ("import os\nk = os.killpg\n", "process"),
]


@pytest.mark.parametrize(("source", "fragment"), BYPASSES, ids=[b[0] for b in BYPASSES])
def test_confirmed_bypasses_are_caught(source: str, fragment: str) -> None:
    assert_flags(source, fragment, "byte_census/scan_module.py")


def test_relative_imports_resolve_against_the_module_package() -> None:
    source = "from ..runner import subprocess\n"

    assert_flags(source, "byte_census.runner.subprocess", "byte_census/legacy/scan.py")


def test_unlisted_import_names_the_module() -> None:
    (found,) = violations("import gzip\n")

    assert found.reason == "import of gzip is not in the module allowlist"


@pytest.mark.parametrize(
    "source",
    [
        "x = {}.copy()\n",
        "import os\nenv = os.environ.copy()\n",
        "name = 'a'.replace('a', 'b', 1)\n",
        "when = moment.replace(tzinfo=None)\n",
        "flags = getattr(info, 'st_flags', 0)\n",
        "from byte_census.legacy.consoles import console\nconsole.print('x')\n",
        "from . import paths\npaths.validate_root('x')\n",
        "import io\nbuffer = io.StringIO()\n",
        "import json, re, time, datetime, enum, hashlib, stat, sys, typing\n",
        "import sys\nsys.exit(0)\n",
        "from rich.progress import track\n",
        "import click\n@click.command()\ndef f():\n    pass\n",
        "from pathlib import Path\nkind = Path\n",
        "if __name__ == '__main__':\n    pass\n",
    ],
)
def test_ordinary_code_passes(source: str) -> None:
    assert violations(source) == []


def test_runner_may_reference_its_process_defaults() -> None:
    source = (
        "import os, shutil, subprocess, signal, time\n"
        "def run(launcher=subprocess.Popen, which=shutil.which, killpg=os.killpg,"
        " clock=time.monotonic):\n"
        "    killpg(1, signal.SIGKILL)\n"
    )

    assert violations(source, RUNNER) == []


def test_module_allowlist_is_exactly_documented() -> None:
    assert MODULE_ALLOWLIST == frozenset(
        {
            "__future__",
            "collections",
            "collections.abc",
            "contextlib",
            "csv",
            "dataclasses",
            "datetime",
            "enum",
            "errno",
            "hashlib",
            "io",
            "json",
            "os",
            "os.path",
            "pathlib",
            "re",
            "selectors",
            "shutil",
            "signal",
            "stat",
            "subprocess",
            "sys",
            "time",
            "typing",
            "unicodedata",
            "click",
            "rich",
            "rich.console",
            "rich.progress",
            "rich.table",
            "rich.text",
        }
    )
    assert PACKAGE_ALLOWLIST == ("byte_census",)


def test_every_allowed_module_has_an_attribute_allowlist() -> None:
    assert set(ATTRIBUTE_ALLOWLISTS) == set(MODULE_ALLOWLIST)


# Second security review: chains through modules, unpacking, attribute allowlists.

SECOND_REVIEW_BYPASSES = [
    ("import contextlib\ncontextlib.os.remove(p)\n", "contextlib.os"),
    ("import os.path\nos.path.os.unlink(p)\n", "os.path.os"),
    ("from os.path import os as o2\n", "os.path.os"),
    ("import rich.console\nrich.console.os.remove(p)\n", "rich.console.os"),
    ("import json\njson.codecs.open('x', 'w')\n", "json.codecs"),
    (
        "import csv\ncsv.types.FunctionType(compile('1', 'x', 'eval'), {})()\n",
        "csv.types",
    ),
    ("open(p, **{'mode': 'w'})\n", "unpacking"),
    ("from pathlib import Path\nPath(p).open(**{'mode': 'a'})\n", "unpacking"),
    ("import click\nclick.utils.open_file(p, 'w')\n", "click.utils"),
    ("import click\nclick.termui.launch(p)\n", "click.termui"),
    (
        "import click\nclick.testing.CliRunner().isolated_filesystem()\n",
        "click.testing",
    ),
    ("from click.testing import CliRunner\n", "click.testing"),
    (
        "import contextlib\ngetattr(contextlib, 'os').remove(p)\n",
        "getattr on contextlib",
    ),
    ("import contextlib\nm = contextlib.os\nm.remove(p)\n", "contextlib.os"),
    ("m.remove(p)\n", "remove"),
    ("open(*args)\n", "unpacking"),
    ("import io\nio.open(p, *rest)\n", "io.open"),
    ("import os\nos.open(p, *flags)\n", "unpacking"),
    ("import os\nos.open(p, **options)\n", "unpacking"),
    ("from pathlib import Path\nPath.open(p, *rest)\n", "unpacking"),
    ("import json\njson.dump(data, handle)\n", "not in the json allowlist"),
    ("import time\nclock = time\n", "used as a value"),
    ("import rich\nrich.get_console()\n", "not in the rich allowlist"),
    ("import datetime\ndatetime.datetime.sys\n", "passes through a module"),
    ("import errno\nerrno.os\n", "errno.os"),
    ("import stat\nstat.os\n", "stat.os"),
    ("x.rmtree('d')\n", "rmtree"),
    ("x.truncate(0)\n", "truncate"),
    ("x.makedirs('d')\n", "makedirs"),
    ("x.utime(p)\n", "utime"),
    ("x.copyfile('a', 'b')\n", "copyfile"),
]


@pytest.mark.parametrize(
    ("source", "fragment"),
    SECOND_REVIEW_BYPASSES,
    ids=[b[0] for b in SECOND_REVIEW_BYPASSES],
)
def test_second_review_bypasses_are_caught(source: str, fragment: str) -> None:
    assert_flags(source, fragment)


@pytest.mark.parametrize(
    "source",
    [
        "import stat\nclass Entry:\n    stat: int\n",
        "import datetime\nnow = datetime.datetime.now()\n",
        "import errno\ncode = errno.EACCES\nname = errno.errorcode.get(1)\n",
        "import sys\nsys.stdout.isatty()\n",
        (
            "import click\n@click.option('--x', type=click.Choice(['a']))\n"
            "def f(x):\n    click.echo(x)\n"
        ),
        "from rich.console import Console\nConsole(stderr=True)\n",
        "items = []\nitems.pop()\n",
    ],
)
def test_allowlisted_attribute_use_passes(source: str) -> None:
    assert violations(source) == []


# Third review: package modules as values, frame and traceback attributes.

THIRD_REVIEW_BYPASSES = [
    ("from byte_census import fsread\nm = fsread\nm.os.system('x')\n", "fsread"),
    ("from byte_census import fsread\n[fsread][0].os.system('x')\n", "fsread"),
    ("from byte_census import fsread\nfsread.os.system('x')\n", "reaches os"),
    ("import byte_census.fsread\nm = byte_census.fsread\n", "used as a value"),
    ("import byte_census\nm = byte_census\n", "used as a value"),
    ("from byte_census import legacy\nm = legacy\n", "used as a value"),
    ("from byte_census.legacy import scan\nhelper(scan)\n", "used as a value"),
    ("from . import runner\nm = runner\n", "used as a value"),
    ("g.gi_frame.f_builtins['open'](p, 'w')\n", "gi_frame"),
    ("g.gi_frame.f_builtins['open'](p, 'w')\n", "f_builtins"),
    ("g.gi_frame.f_globals['os'].system('x')\n", "f_globals"),
    ("e.__traceback__.tb_frame.f_builtins['open']\n", "__traceback__"),
    ("e.__traceback__.tb_frame.f_builtins['open']\n", "tb_frame"),
    ("x = c.cr_frame\n", "cr_frame"),
    ("x = a.ag_frame\n", "ag_frame"),
    ("x = g.gi_code\n", "gi_code"),
    ("x = c.cr_code\n", "cr_code"),
    ("x = t.tb_next\n", "tb_next"),
    ("x = f.f_locals\n", "f_locals"),
    ("x = f.f_back\n", "f_back"),
    ("x = f.f_code\n", "f_code"),
    ("x = o.__reduce__()\n", "__reduce__"),
    ("x = getattr(g, 'gi_frame')\n", "gi_frame"),
    ("from byte_census import fsread\nx = fsread.__traceback__\n", "__traceback__"),
]


@pytest.mark.parametrize(
    ("source", "fragment"),
    THIRD_REVIEW_BYPASSES,
    ids=[b[0] for b in THIRD_REVIEW_BYPASSES],
)
def test_third_review_bypasses_are_caught(source: str, fragment: str) -> None:
    assert_flags(source, fragment)


@pytest.mark.parametrize(
    "source",
    [
        "from byte_census import fsread\nfsread.walk('.')\n",
        "from byte_census.fsread import walk\nhelper(walk)\n",
        "from byte_census.render import render\nrender({}, 'json')\n",
        "from byte_census import runner\nerror = runner.RunnerError\n",
    ],
)
def test_package_names_that_are_not_modules_pass(source: str) -> None:
    assert violations(source) == []


@pytest.mark.parametrize(
    "name",
    [
        "gi_frame",
        "cr_frame",
        "ag_frame",
        "gi_code",
        "cr_code",
        "tb_frame",
        "tb_next",
        "f_globals",
        "f_builtins",
        "f_locals",
        "f_back",
        "f_code",
        "__traceback__",
        "__globals__",
        "__code__",
        "__closure__",
        "__func__",
        "__self__",
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__getattribute__",
        "__reduce__",
    ],
)
def test_introspection_attributes_are_forbidden_in_any_position(name: str) -> None:
    assert_flags(f"x = y.{name}\n", name)
    assert_flags(f"import os\nx = os.{name}\n", name)


# Closing review: content reads and directory enumeration outside fsread.

CHECK_MODULE = "byte_census/checks/new_check.py"

READERS = [
    "open(p)\n",
    "open(p, 'rb')\n",
    "open(p, mode='r')\n",
    "from pathlib import Path\nPath(p).open()\n",
    "from pathlib import Path\nPath(p).open('rb')\n",
    "from pathlib import Path\nPath(p).read_bytes()\n",
    "from pathlib import Path\nPath(p).read_text()\n",
    "from pathlib import Path\nPath.read_bytes(p)\n",
    "from pathlib import Path\nPath.read_text(p)\n",
    "reader = p.read_bytes\n",
    "getattr(p, 'read_text')()\n",
    "import os\nos.open(p, os.O_RDONLY)\n",
    "import os\nos.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)\n",
]

ENUMERATORS = [
    "import os\nos.scandir(p)\n",
    "import os\nos.listdir(p)\n",
    "import os\nos.walk(p)\n",
    "from os import scandir\nscandir(p)\n",
    "from pathlib import Path\nPath(p).iterdir()\n",
    "from pathlib import Path\nPath(p).glob('*')\n",
    "from pathlib import Path\nPath(p).rglob('*')\n",
    "from pathlib import Path\nPath(p).walk()\n",
    "from pathlib import Path\nPath.rglob(p, '*')\n",
    "lister = p.iterdir\n",
    "getattr(p, 'glob')('*')\n",
]


@pytest.mark.parametrize("source", READERS)
def test_content_reads_outside_fsread_are_flagged(source: str) -> None:
    assert_flags(source, "content read outside", CHECK_MODULE)


@pytest.mark.parametrize("source", READERS)
def test_content_reads_are_allowed_in_fsread(source: str) -> None:
    assert violations(source, FSREAD) == []


@pytest.mark.parametrize("source", ENUMERATORS)
def test_enumeration_outside_fsread_is_flagged(source: str) -> None:
    assert_flags(source, "directory enumeration outside", CHECK_MODULE)


@pytest.mark.parametrize("source", ENUMERATORS)
def test_enumeration_is_allowed_in_fsread(source: str) -> None:
    assert violations(source, FSREAD) == []


@pytest.mark.parametrize("source", ENUMERATORS)
def test_writer_may_not_enumerate(source: str) -> None:
    assert_flags(source, "directory enumeration outside", WRITER)


def test_writer_may_open_its_output() -> None:
    source = (
        "import os\nfd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL)\n"
        "handle = os.fdopen(fd, 'w')\n"
    )

    assert violations(source, WRITER) == []


def test_fsread_still_may_not_open_for_writing() -> None:
    assert_flags("import os\nos.open(p, os.O_WRONLY)\n", "os.open", FSREAD)
    assert_flags("open(p, 'w')\n", "open", FSREAD)


def test_walking_through_fsread_is_allowed_everywhere() -> None:
    source = (
        "from byte_census import fsread\nfor item in fsread.walk(root):\n    pass\n"
    )

    assert violations(source, CHECK_MODULE) == []
