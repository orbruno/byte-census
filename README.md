# byte-census

Author: Orlando Bruno | Version: 2.0.0

byte-census is a read-only command-line census of the bytes on a macOS disk. It reports where the space is, which folders can be regenerated, and what looks like a cleanup candidate, as JSON for programs or a table for people. It observes and suggests; it never deletes, moves, or changes anything.

The package also ships `dupfind`, the original duplicate finder, kept as a frozen legacy command (see [Legacy: dupfind](#legacy-dupfind)).

For an agent that has never seen the tool, start with [SKILL.md](SKILL.md).

## Install

Python commands run through [uv](https://docs.astral.sh/uv/). From a clone of this repository:

```bash
uv tool install --editable .
byte-census --version
```

Without installing, run in the project environment:

```bash
uv sync
uv run byte-census --help
```

Requires Python 3.11 or newer and macOS.

## Commands

There are five commands. Four use the `scan` verb; `disk map` is the exception.

## Command overview

<!-- help: byte-census -->
```text
Usage: byte-census [OPTIONS] COMMAND [ARGS]...

  Census of the bytes on disk.

  Example:

      # Show the version
      byte-census --version

Options:
  --version   Show the version and exit.
  -h, --help  Show this message and exit.

Commands:
  artifacts   Find regenerable development folders.
  caches      Find the largest caches.
  disk        Map where the data volume's used space is.
  docker      Observe Docker's own disk accounting.
  duplicates  Find files with identical content.
```

### docker scan

Docker's own accounting of images, containers, volumes, and build cache. Exits 4 when Docker is missing or not running.

<!-- help: byte-census docker scan -->
```text
Usage: byte-census docker scan [OPTIONS]

  Report Docker disk usage, images, and stopped containers.

  Figures are Docker-reported and are never added to host totals. Exits 4 when
  the Docker CLI is missing or the daemon is not running. Nothing is changed.

  Example:

      byte-census docker scan --format table

Options:
  --format [json|table]  Output format: JSON for programs, table for people.
                         [default: json]
  -h, --help             Show this message and exit.
```

### caches scan

The largest folders in `~/Library/Caches` plus the uv, npm, and Homebrew caches.

<!-- help: byte-census caches scan -->
```text
Usage: byte-census caches scan [OPTIONS]

  Report the largest folders in ~/Library/Caches and the uv, npm, and Homebrew
  caches. Read-only; it never deletes anything.

  Example:

      # The five largest caches, as a table
      byte-census caches scan --top 5 --format table

Options:
  --top INTEGER RANGE    Show only this many largest caches; totals cover all of
                         them.  [default: 20; x>=1]
  --format [json|table]  Output format: JSON for programs, table for people.
                         [default: json]
  -h, --help             Show this message and exit.
```

### artifacts scan

Regenerable development folders (`node_modules`, `.venv`, `venv`, `target`) with the command that rebuilds each.

<!-- help: byte-census artifacts scan -->
```text
Usage: byte-census artifacts scan [OPTIONS] ROOT

  List node_modules, .venv, venv, and target folders under ROOT.

  Each one is reported with its allocated size, its project, the project's
  modification time, and the command that regenerates it. Nothing is removed;
  the removal command is a suggestion only.

  Example:

      byte-census artifacts scan ~/Projects --format table

Options:
  --format [json|table]  Output format: JSON for programs, table for people.
                         [default: json]
  -h, --help             Show this message and exit.
```

### duplicates scan

Files with identical content, grouped by size, a hash of the first 64 KiB, then a full SHA-256.

<!-- help: byte-census duplicates scan -->
```text
Usage: byte-census duplicates scan [OPTIONS] PATH

  Find duplicate files under PATH, reading as little content as possible.

  Files are grouped by size, then by a SHA-256 of their first 64 KiB, then by a
  full SHA-256. Hard links count as one copy. Nothing is deleted; suggestions
  are text only and need the owner's authorization.

  Example:

      # Duplicates of at least 1 MiB in Downloads
      byte-census duplicates scan ~/Downloads --min-size 1048576
      
      # Content present both in Downloads and in an archive
      byte-census duplicates scan ~/Downloads --compare /Volumes/Archive

Options:
  --compare PATH                Report only content found both under PATH and
                                under this directory.
  --min-size INTEGER RANGE      Ignore files smaller than this many bytes. Empty
                                files are always ignored.  [default: 0; x>=0]
  --recursive / --no-recursive  Descend into subdirectories.  [default:
                                recursive]
  --format [json|table]         Output format: JSON for programs, table for
                                people.  [default: json]
  -h, --help                    Show this message and exit.
```

### disk map

Where the used space of the data volume is, reconciled against `df`. It needs at least one `--scan-root`, and it reads inside privacy-protected folders, so macOS may show a permission prompt. A denial is recorded in `incomplete_coverage`, not raised as an error.

<!-- help: byte-census disk map -->
```text
Usage: byte-census disk map [OPTIONS]

  Measure each scan root on the data volume, its largest first-level folders and
  large files, the macOS categories (caches, application support, containers,
  developer data, backups, Mail, Messages, Downloads, Applications) and the uv,
  npm, and Homebrew caches, then reconcile the total with `df -k
  /System/Volumes/Data`. Overlapping scopes are shown but counted once; hard
  links are counted once. System context (`df -k /`, `diskutil info /`, local
  snapshots, Docker) is informational. Read-only; it never suggests or deletes
  anything.

  Example:

      # Two roots, ten folders each
      byte-census disk map --scan-root ~/Library --scan-root ~/Documents --top 10
      
      # Files over 1 GiB, as a table
      byte-census disk map --scan-root ~ --large-file-min 1024 --format table

Options:
  --scan-root PATH            Folder on the data volume to measure. Repeat for
                              several roots.  [required]
  --top INTEGER RANGE         Show this many largest first-level folders per
                              root; totals cover all.  [default: 30; x>=1]
  --large-file-min MB         List files larger than this many MiB (20 largest
                              per root).  [default: 500; x>=0]
  --skip-categories           Measure only the scan roots: no macOS categories
                              and no tool caches.
  --tree-depth INTEGER RANGE  Folder levels below each root shown in the tree.
                              [default: 4; x>=0]
  --tree-min-mb MB            Show only tree folders of at least this many MiB.
                              [default: 100; x>=0]
  --format [json|table]       Output format: JSON for programs, table for
                              people.  [default: json]
  -h, --help                  Show this message and exit.
```

## Read-only guarantee

Every command only reads. A test parses the source and fails if any module outside a short allowlist can write, delete, rename, change permissions, or start a process. External programs (`df`, `diskutil`, `tmutil`, `docker`) run only from a fixed argument list. Cleanup suggestions in the output are text with `requires_owner_authorization: true`; nothing in byte-census runs them, and they must not be run without the owner's approval. The model covers a careless caller and a changing filesystem, not a hostile one; byte sizes, hard links, volume boundaries, and privacy denials are defined in [docs/contracts/quantities.md](docs/contracts/quantities.md).

## Output contract

JSON is the default, printed as `{"data": ..., "meta": ...}`. Use `--format table` for people. Findings, suggestions, status, coverage gaps, and the error object are specified in [docs/contracts/](docs/contracts/), with one example per command in `docs/contracts/examples/`. `meta.schema_version` versions the contract independently from the package.

## Exit codes

- 0: success, including `status: partial`
- 1: internal error
- 2: usage error
- 3: validation error (for example a missing scan root)
- 4: a required source is unavailable (Docker not running, `df` failed)

Errors are a JSON object on stderr.

## Legacy: dupfind

`dupfind` is the v1 duplicate finder. It is deprecated and frozen: its options, table, JSON, and CSV output, and exit codes stay as they were. Use `byte-census duplicates scan` for new work. Its specification is in [SPECIFICATION.md](SPECIFICATION.md); the exit-code matrix is in [docs/contracts/legacy-exit-codes.md](docs/contracts/legacy-exit-codes.md).

```bash
uv run dupfind ~/Downloads --min-size 1048576 --format json
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
```

The README help blocks above are checked against the live `--help` output by `tests/test_readme_help.py`. When a command's help changes, update the matching block.

## Project documents

- Decision record: [ADR-001, Python implementation language](docs/adr/ADR-001__fw__python-implementation-language.md)
- Backlog: [_Project-Management/Backlog/product-backlog.md](_Project-Management/Backlog/product-backlog.md)
- Definition of Done: [_Project-Management/Definition-of-Done.md](_Project-Management/Definition-of-Done.md)
- Changes: [CHANGELOG.md](CHANGELOG.md)

## License

No license file is currently included. Choose a license before distributing the project for third-party reuse.
