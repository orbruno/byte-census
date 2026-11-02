"""`byte-census duplicates scan` (WI-DUPLICATES AC-01 to AC-08).

Fixture trees are built in tmp_path. Files larger than 64 KiB use 100 KiB of
content so the partial and full stages are distinguishable in the byte count.
"""

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from byte_census import fsread
from byte_census.checks import duplicates_hash
from byte_census.cli import main
from tests.support.snapshots import allocated_bytes_of, assert_json_snapshot

KIB = 1024
PARTIAL = 64 * KIB
BIG = 100 * KIB
ERROR_KEYS = [
    "schema_version",
    "error",
    "reason",
    "suggestion",
    "help",
    "code",
    "exit_code",
]


def invoke(args: list[str], **kwargs: Any) -> Result:
    return CliRunner().invoke(main, args, **kwargs)


def scan(*args: str) -> dict[str, Any]:
    result = invoke(["duplicates", "scan", *args])
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    return json.loads(result.stdout)


def error_of(result: Result) -> dict[str, Any]:
    assert result.stdout == ""
    assert result.stderr.count("\n") == 1, repr(result.stderr)
    payload = json.loads(result.stderr)
    assert list(payload) == ERROR_KEYS
    assert payload["exit_code"] == result.exit_code
    assert "Traceback" not in result.stderr
    return payload


def big(head: bytes, tail: bytes = b"t") -> bytes:
    """100 KiB: a 64 KiB head made of `head`, then a tail made of `tail`."""
    return (head * PARTIAL)[:PARTIAL] + (tail * BIG)[: BIG - PARTIAL]


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Two big copies (one hard-linked), a near copy, a size-only match,
    two small copies, empty files, and a unique file."""
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "a.bin").write_bytes(big(b"A"))
    (root / "b.bin").write_bytes(big(b"A"))
    os.link(root / "a.bin", root / "sub" / "a-link.bin")
    (root / "c.bin").write_bytes(big(b"A", b"u"))
    (root / "d.bin").write_bytes(big(b"D"))
    (root / "s1.txt").write_bytes(b"small copy")
    (root / "sub" / "s2.txt").write_bytes(b"small copy")
    (root / "e1").write_bytes(b"")
    (root / "e2").write_bytes(b"")
    (root / "unique.bin").write_bytes(b"x" * 3000)
    return root


def groups(payload: dict[str, Any]) -> list[list[str]]:
    return [
        [entry["path"] for entry in finding["details"]["files"]]
        for finding in payload["data"]["findings"]
    ]


def test_stages_find_exact_duplicates_only(tree: Path) -> None:
    payload = scan(str(tree))
    base = str(tree.resolve())

    assert groups(payload) == [
        [f"{base}/a.bin", f"{base}/b.bin"],
        [f"{base}/s1.txt", f"{base}/sub/s2.txt"],
    ]
    assert payload["data"]["summary"] == {
        "files_considered": 7,
        "size_candidates": 6,
        "partial_hash_candidates": 5,
        "duplicate_groups": 2,
        "duplicate_copies": 4,
        "reclaimable_estimate_bytes": allocated_bytes_of(tree / "b.bin")
        + allocated_bytes_of(tree / "sub" / "s2.txt"),
    }
    assert payload["meta"]["status"] == "complete"


def test_content_bytes_read_equals_bytes_hashed(tree: Path) -> None:
    payload = scan(str(tree))

    # Stage 2: four 100 KiB size candidates read 64 KiB each and two small
    # files are read once in full. Stage 3: three partial matches read fully.
    expected = 4 * PARTIAL + 2 * len(b"small copy") + 3 * BIG
    assert payload["meta"]["cost"]["content_bytes_read"] == expected


def test_reads_match_cost_counter(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_read = os.read
    total = {"bytes": 0}

    def counting_read(fd: int, size: int) -> bytes:
        chunk = real_read(fd, size)
        total["bytes"] += len(chunk)
        return chunk

    monkeypatch.setattr(duplicates_hash.os, "read", counting_read)
    payload = scan(str(tree))

    assert payload["meta"]["cost"]["content_bytes_read"] == total["bytes"]


def test_small_files_are_opened_once(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []
    real = fsread.open_regular_file

    def spy(path: Any) -> Any:
        opened.append(os.path.basename(os.fspath(path)))
        return real(path)

    monkeypatch.setattr(fsread, "open_regular_file", spy)
    scan(str(tree))

    assert opened.count("s1.txt") == 1
    assert opened.count("s2.txt") == 1
    assert opened.count("a.bin") == 2
    assert opened.count("d.bin") == 1
    assert "unique.bin" not in opened
    assert "e1" not in opened


def test_small_group_has_equal_partial_and_content_hash(tree: Path) -> None:
    payload = scan(str(tree))
    small = payload["data"]["findings"][1]["details"]

    assert small["partial_sha256"] == small["content_sha256"]
    assert small["file_logical_bytes"] == len(b"small copy")


def test_hard_links_merge_and_never_count_as_waste(tree: Path) -> None:
    payload = scan(str(tree))
    finding = payload["data"]["findings"][0]
    a_alloc = allocated_bytes_of(tree / "a.bin")
    b_alloc = allocated_bytes_of(tree / "b.bin")

    files = finding["details"]["files"]
    assert files[0]["hard_link_paths"] == [str(tree.resolve() / "sub" / "a-link.bin")]
    assert finding["details"]["copy_count"] == 2
    assert finding["logical_bytes"] == 2 * BIG
    assert finding["allocated_bytes"] == a_alloc + b_alloc
    assert finding["reclaimable_estimate_bytes"] == b_alloc
    assert finding["caveats"] == ["apfs_clone_or_shared_extent", "hard_links_merged"]


def test_hard_links_alone_are_not_duplicates(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.bin").write_bytes(big(b"Q"))
    os.link(root / "one.bin", root / "two.bin")

    payload = scan(str(root))

    assert payload["data"]["findings"] == []
    assert payload["data"]["summary"]["files_considered"] == 1
    assert payload["meta"]["cost"]["content_bytes_read"] == 0


def test_hard_link_primary_is_shallowest_name(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "archive").mkdir(parents=True)
    (root / "report.pdf").write_bytes(b"same")
    os.link(root / "report.pdf", root / "archive" / "link.pdf")
    (root / "report (1).pdf").write_bytes(b"same")

    files = scan(str(root))["data"]["findings"][0]["details"]["files"]
    base = str(root.resolve())

    assert files == [
        {
            "path": f"{base}/report (1).pdf",
            "allocated_bytes": allocated_bytes_of(root / "report (1).pdf"),
            "hard_link_paths": [],
        },
        {
            "path": f"{base}/report.pdf",
            "allocated_bytes": allocated_bytes_of(root / "report.pdf"),
            "hard_link_paths": [f"{base}/archive/link.pdf"],
        },
    ]


def test_suggestion_removes_every_name_except_the_kept_copy(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "archive").mkdir(parents=True)
    (root / "report.pdf").write_bytes(b"same")
    os.link(root / "report.pdf", root / "archive" / "link.pdf")
    (root / "report (1).pdf").write_bytes(b"same")
    base = str(root.resolve())

    payload = scan(str(root))
    finding = payload["data"]["findings"][0]
    (suggestion,) = payload["data"]["suggestions"]

    assert suggestion["id"] == f"duplicate-remove-extra-copies@{finding['id']}"
    assert suggestion["command"] == (
        f"rm -- '{base}/report.pdf' && rm -- '{base}/archive/link.pdf'"
    )
    assert suggestion["risk"] == "high"
    assert suggestion["reversible"] is False
    assert suggestion["requires_owner_authorization"] is True
    assert f"'{base}/report (1).pdf'" in suggestion["reason"]
    assert suggestion["finding_ids"] == [finding["id"]]
    assert finding["suggestion_ids"] == [suggestion["id"]]


def test_finding_id_follows_content_hash(tree: Path) -> None:
    finding = scan(str(tree))["data"]["findings"][0]

    assert finding["kind"] == "duplicate_group"
    assert finding["target"] == "sha256:" + finding["details"]["content_sha256"]
    assert finding["see_check"] is None
    assert finding["classification"]["owner"] == ""


def test_empty_files_are_excluded(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for name in ("x", "y", "z"):
        (root / name).write_bytes(b"")

    payload = scan(str(root))

    assert payload["data"]["findings"] == []
    assert payload["data"]["summary"]["files_considered"] == 0


def test_min_size_excludes_smaller_files(tree: Path) -> None:
    payload = scan(str(tree), "--min-size", "1000")

    assert len(groups(payload)) == 1
    assert payload["meta"]["scope"]["options"] == {
        "compare": None,
        "min_size": 1000,
        "recursive": True,
    }
    assert payload["meta"]["cost"]["content_bytes_read"] == 4 * PARTIAL + 3 * BIG


def test_no_recursive_stays_at_top_level(tree: Path) -> None:
    payload = scan(str(tree), "--no-recursive")
    base = str(tree.resolve())

    assert groups(payload) == [[f"{base}/a.bin", f"{base}/b.bin"]]
    files = payload["data"]["findings"][0]["details"]["files"]
    assert files[0]["hard_link_paths"] == []
    assert payload["meta"]["scope"]["options"]["recursive"] is False
    assert payload["data"]["findings"][0]["caveats"] == ["apfs_clone_or_shared_extent"]


def test_no_recursive_records_unreadable_entries(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = fsread.lstat

    def failing(path: Any) -> os.stat_result:
        text = os.fspath(path)
        if text.endswith("unique.bin"):
            raise PermissionError(13, "denied", text)
        return real(path)

    monkeypatch.setattr(fsread, "lstat", failing)
    payload = scan(str(tree), "--no-recursive")

    assert payload["meta"]["incomplete_coverage"] == [
        {
            "path": str(tree.resolve() / "unique.bin"),
            "reason": "permission_denied",
            "errno": "EACCES",
            "operation": "lstat",
        }
    ]


def test_no_recursive_root_listing_error(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(path: Any) -> Any:
        raise PermissionError(1, "not permitted", os.fspath(path))

    monkeypatch.setattr(duplicates_scan_module().os, "scandir", failing)
    payload = scan(str(tree), "--no-recursive")

    assert payload["meta"]["incomplete_coverage"] == [
        {
            "path": str(tree.resolve()),
            "reason": "privacy_denied",
            "errno": "EPERM",
            "operation": "scandir",
        }
    ]


def duplicates_scan_module() -> Any:
    from byte_census.checks import duplicates_collect

    return duplicates_collect


def test_compare_reports_only_groups_spanning_both_roots(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "shared.bin").write_bytes(big(b"S"))
    (right / "shared-copy.bin").write_bytes(big(b"S"))
    (left / "only-left-1.txt").write_bytes(b"left twin")
    (left / "only-left-2.txt").write_bytes(b"left twin")

    payload = scan(str(left), "--compare", str(right))

    assert groups(payload) == [
        [str(left.resolve() / "shared.bin"), str(right.resolve() / "shared-copy.bin")]
    ]
    roots = [root["path"] for root in payload["meta"]["scope"]["roots"]]
    assert roots == [str(left.resolve()), str(right.resolve())]
    assert payload["meta"]["scope"]["options"]["compare"] == str(right.resolve())
    # The left-only twins never reach the hashing stages.
    assert payload["meta"]["cost"]["content_bytes_read"] == 2 * PARTIAL + 2 * BIG


def changing_opener(
    target: str, on_call: int, action: Callable[[Path], None]
) -> Callable[[Any], Any]:
    """Wrap the safe opener so `action` runs before the n-th open of target."""
    real = fsread.open_regular_file
    seen = {"count": 0}

    @contextmanager
    def opener(path: Any) -> Iterator[int]:
        if os.path.basename(os.fspath(path)) == target:
            seen["count"] += 1
            if seen["count"] == on_call:
                action(Path(os.fspath(path)))
        with real(path) as fd:
            yield fd

    return opener


def grow(path: Path) -> None:
    with path.open("ab") as handle:
        handle.write(b"more")


def touch_mtime(path: Path) -> None:
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 5_000_000_000))


def coverage_of(payload: dict[str, Any]) -> list[tuple[str, str, Any, str]]:
    return [
        (
            os.path.basename(entry["path"]),
            entry["reason"],
            entry["errno"],
            entry["operation"],
        )
        for entry in payload["meta"]["incomplete_coverage"]
    ]


@pytest.mark.parametrize("action", [grow, touch_mtime])
@pytest.mark.parametrize("on_call", [1, 2])
def test_changed_file_is_excluded_and_listed(
    tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: Callable[[Path], None],
    on_call: int,
) -> None:
    monkeypatch.setattr(
        fsread, "open_regular_file", changing_opener("b.bin", on_call, action)
    )
    payload = scan(str(tree))

    assert payload["meta"]["status"] == "partial"
    assert coverage_of(payload) == [("b.bin", "changed_during_scan", None, "hash")]
    assert all("b.bin" not in p for g in groups(payload) for p in g)


def test_file_changed_during_read_is_excluded(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_read = os.read
    state = {"done": False}

    def read_then_grow(fd: int, size: int) -> bytes:
        chunk = real_read(fd, size)
        if not state["done"] and os.fstat(fd).st_ino == os.stat(tree / "b.bin").st_ino:
            state["done"] = True
            grow(tree / "b.bin")
        return chunk

    monkeypatch.setattr(duplicates_hash.os, "read", read_then_grow)
    payload = scan(str(tree))

    assert coverage_of(payload) == [("b.bin", "changed_during_scan", None, "hash")]


def test_vanished_file_is_excluded_and_listed(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        fsread,
        "open_regular_file",
        changing_opener("b.bin", 2, lambda path: path.unlink()),
    )
    payload = scan(str(tree))

    assert coverage_of(payload) == [("b.bin", "vanished", "ENOENT", "open")]
    base = str(tree.resolve())
    assert groups(payload) == [[f"{base}/s1.txt", f"{base}/sub/s2.txt"]]


def test_file_replaced_by_directory_is_changed(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def to_directory(path: Path) -> None:
        path.unlink()
        path.mkdir()

    monkeypatch.setattr(
        fsread, "open_regular_file", changing_opener("d.bin", 1, to_directory)
    )
    payload = scan(str(tree))

    assert coverage_of(payload) == [("d.bin", "changed_during_scan", None, "hash")]


def test_read_error_is_listed(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_read(fd: int, size: int) -> bytes:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(duplicates_hash.os, "read", failing_read)
    payload = scan(str(tree))

    reasons = {entry[1:] for entry in coverage_of(payload)}
    assert reasons == {("read_error", "EIO", "read")}
    assert payload["data"]["findings"] == []
    assert payload["meta"]["cost"]["content_bytes_read"] == 0


def test_dataless_file_is_never_opened(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataless_ino = os.stat(tree / "b.bin").st_ino
    real = fsread.is_dataless

    def fake(info: Any) -> bool:
        return getattr(info, "st_ino", None) == dataless_ino or real(info)

    monkeypatch.setattr(fsread, "is_dataless", fake)
    payload = scan(str(tree))

    assert coverage_of(payload) == [("b.bin", "dataless", None, "lstat")]
    assert all("b.bin" not in p for g in groups(payload) for p in g)


def test_dataless_at_open_is_listed(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(path: Any) -> Any:
        raise fsread.DatalessFileError(path)

    real = fsread.open_regular_file

    def opener(path: Any) -> Any:
        if os.path.basename(os.fspath(path)) == "d.bin":
            return refuse(path)
        return real(path)

    monkeypatch.setattr(fsread, "open_regular_file", opener)
    payload = scan(str(tree))

    assert coverage_of(payload) == [("d.bin", "dataless", None, "open")]


def test_walk_errors_become_incomplete_coverage(tree: Path) -> None:
    locked = tree / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        payload = scan(str(tree))
    finally:
        locked.chmod(0o755)

    assert coverage_of(payload) == [
        ("locked", "permission_denied", "EACCES", "scandir")
    ]


def test_entries_visited_counts_every_entry(tree: Path) -> None:
    payload = scan(str(tree))

    # 10 files and links plus the `sub` directory.
    assert payload["meta"]["cost"]["entries_visited"] == 11
    assert payload["meta"]["cost"]["subprocess_calls"] == 0


def test_sparse_file_caveat(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    for name in ("one", "two"):
        with (root / name).open("wb") as handle:
            handle.seek(8 * 1024 * 1024)
            handle.write(b"end")

    finding = scan(str(root))["data"]["findings"][0]

    if finding["logical_bytes"] > finding["allocated_bytes"]:
        assert "sparse_file" in finding["caveats"]


def embedded_roots_masked(payload: dict[str, Any], roots: list[Path]) -> Any:
    """Mask roots inside suggestion strings, where they follow a quote.

    The snapshot helper masks only strings that start with a root; suggestion
    commands and reasons quote paths mid-string.
    """
    text = json.dumps(payload)
    for root in sorted({str(r) for r in roots}, key=len, reverse=True):
        text = text.replace(f"'{root}/", "'<ROOT>/")
    return json.loads(text)


def test_snapshot(tree: Path) -> None:
    roots = [tree, tree.resolve()]
    payload = embedded_roots_masked(scan(str(tree)), roots)

    assert_json_snapshot(payload, "duplicates-scan", roots=roots)


def test_table_format(tree: Path) -> None:
    result = invoke(["duplicates", "scan", str(tree), "--format", "table"])

    assert result.exit_code == 0
    assert "duplicate_group" in result.stdout
    assert "duplicate-remove-extra-copies@" in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["duplicates", "scan"],
        ["duplicates", "scan", "PATH", "--format", "csv"],
        ["duplicates", "scan", "PATH", "--output", "x.csv"],
        ["duplicates", "scan", "PATH", "--min-size", "-1"],
        ["duplicates", "scan", "PATH", "--min-size", "abc"],
        ["duplicates", "scan", "PATH", "--min-size"],
        ["duplicates", "scan", "PATH", "--compare"],
        ["duplicates", "bogus"],
    ],
)
def test_usage_errors_exit_2(tree: Path, args: list[str]) -> None:
    result = invoke([str(tree) if a == "PATH" else a for a in args])

    assert result.exit_code == 2
    payload = error_of(result)
    assert payload["code"] == "usage_error"


@pytest.mark.parametrize("args", [["--min-size"], ["--compare"], ["--bogus"]])
def test_usage_error_help_names_scan(tree: Path, args: list[str]) -> None:
    payload = error_of(invoke(["duplicates", "scan", str(tree), *args]))

    assert payload["help"] == "byte-census duplicates scan --help"


@pytest.mark.parametrize("bad", ["/definitely/not/here", "bad\x01name"])
def test_invalid_path_exits_3(bad: str) -> None:
    result = invoke(["duplicates", "scan", bad])

    assert result.exit_code == 3
    payload = error_of(result)
    assert payload["code"] == "validation_error"
    assert payload["help"] == "byte-census duplicates scan --help"


def test_invalid_compare_exits_3(tree: Path) -> None:
    result = invoke(["duplicates", "scan", str(tree), "--compare", "/not/here"])

    assert result.exit_code == 3
    assert error_of(result)["code"] == "validation_error"


def test_root_that_is_a_file_exits_3(tree: Path) -> None:
    result = invoke(["duplicates", "scan", str(tree / "a.bin")])

    assert result.exit_code == 3


def test_internal_error_exits_1(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(duplicates_hash, "hash_stage", boom)
    result = invoke(["duplicates", "scan", str(tree)])

    assert result.exit_code == 1
    assert error_of(result)["code"] == "internal_error"


@pytest.mark.parametrize("flag", ["-h", "--help"])
@pytest.mark.parametrize("command", [["duplicates"], ["duplicates", "scan"]])
def test_help_starts_with_usage_and_has_example(command: list[str], flag: str) -> None:
    result = invoke([*command, flag])

    assert result.exit_code == 0
    assert result.output.startswith("Usage:")
    assert "Example:" in result.output
    assert "byte-census duplicates scan" in result.output


def test_duplicates_is_listed_in_group_help() -> None:
    assert "duplicates" in invoke(["--help"]).stdout
