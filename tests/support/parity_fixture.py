"""Deterministic fixture tree for the golden parity check (WI-DISK-MAP-TREE).

The same builder produced the committed golden output once, outside the test
suite (tests/fixtures/parity/PROVENANCE.md), and rebuilds the tree in
tmp_path for every parity test. Sizes are distinct so that every ordering
is decided by size alone; there are no hard links, so `du` and byte-census
count every inode the same way.
"""

from pathlib import Path

KIB = 1024
MIB = 1024 * KIB

# Under the scan root: relative path -> size in bytes.
SCAN_FILES: dict[str, int] = {
    "media/movie.mov": 3 * MIB,
    "media/clips/a.mp4": MIB + MIB // 2,
    "archive/old.zip": 2 * MIB,
    "archive/exact.bin": MIB,
    "projects/app/src/deep/deeper/deepest/leaf.txt": 70 * KIB,
    "projects/app/src/main.py": 12 * KIB,
    "projects/app/README.md": 3 * KIB,
    "docs/notes.txt": 40 * KIB,
    "root.bin": MIB + 200 * KIB,
}
SCAN_EMPTY_DIRS = ("empty",)

# Under the fixture home: one folder per managed category, with distinct sizes.
HOME_FILES: dict[str, int] = {
    "Library/Caches/app/c.bin": 300 * KIB,
    "Library/Application Support/Steam/game.pak": 900 * KIB,
    "Library/Application Support/MobileSync/Backup/0000/Manifest.db": 500 * KIB,
    "Library/Containers/com.example/data.bin": 260 * KIB,
    "Library/Group Containers/group.example/g.bin": 120 * KIB,
    "Library/Developer/Xcode/DerivedData/build.o": 700 * KIB,
    "Library/Mail/V10/mail.emlx": 60 * KIB,
    "Library/Messages/chat.db": 90 * KIB,
    "Downloads/setup.dmg": 450 * KIB,
}


def _write(base: Path, files: dict[str, int]) -> None:
    for relative, size in files.items():
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"p" * size)


def build_parity_fixture(base: Path) -> tuple[Path, Path]:
    """Create `<base>/scan` and `<base>/home`; return both."""
    scan, home = base / "scan", base / "home"
    _write(scan, SCAN_FILES)
    for name in SCAN_EMPTY_DIRS:
        (scan / name).mkdir(parents=True, exist_ok=True)
    _write(home, HOME_FILES)
    return scan, home
