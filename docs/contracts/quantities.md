# Quantities, Volume Boundary, and Cost

Author: Orlando Bruno
Contract version: 1.0.0 (see [envelope.md](envelope.md) for the version policy)
Satisfies: WI-CONTRACTS AC-01, AC-02, AC-05, AC-07

Every byte figure in byte-census output is an integer number of bytes. Human units (KB, MB, GB) appear only in `--format table`.

## Glossary

| Field | Definition | Source |
|---|---|---|
| `logical_bytes` | Sum of `st_size` over the regular files a finding covers. Directory and symlink `st_size` values are excluded because they do not describe content. | `lstat` |
| `allocated_bytes` | Sum of `st_blocks x 512` over every entry a finding covers: regular files, directories (each directory's own blocks are counted, as `du` does), symlinks, and special files. | `lstat` |
| `reclaimable_estimate_bytes` | Upper-bound estimate of the allocated space a cleanup of this finding could free. It is an estimate, never a promise (see Limitations). `null` when the check makes no reclaim claim. | Derived per check |
| `docker_reported_size_bytes` | Size as reported by the Docker CLI, converted to bytes. | `docker` output |
| `docker_reported_reclaimable_bytes` | Reclaimable size as reported by the Docker CLI, converted to bytes. | `docker` output |
| `df_used_bytes`, `total_bytes`, `available_bytes` | `df -k` columns multiplied by 1024. | `df -k` |

Per-check meaning of `reclaimable_estimate_bytes`:

| Check | Value |
|---|---|
| `duplicates scan` | Allocated bytes of every distinct inode in a group except one. Hard-linked names of one inode never count. |
| `artifacts scan` | Allocated bytes of the artifact subtree. |
| `caches scan` | Allocated bytes of the cache folder. |
| `docker scan` | `null`. Docker's own estimate is `docker_reported_reclaimable_bytes`. |
| `disk map` | `null`. Disk map is observational. |

Unit rules:

- `st_blocks` is always in 512-byte units on macOS, independent of the filesystem block size.
- Option values named `*_mb` use MiB (1,048,576 bytes), matching `find -size +NM` in storage-inventory.sh.
- Decision: Docker size strings (for example `7.42GB`) are parsed with Docker's decimal base (1 GB = 1,000,000,000 bytes) and the raw string is kept in `details.raw` so the conversion is auditable.

## Hard links

- Identity of a file is the pair `(st_dev, st_ino)`.
- The identity set is global to one check invocation: across all roots, all categories, all workers (WI-PARALLEL-WALK), and both sides of `--compare`.
- The first encounter in sorted traversal order is attributed the bytes. Later encounters add 0 to `logical_bytes` and `allocated_bytes` but still count in `cost.entries_visited`.
- Traversal order is deterministic: directory entries are visited in ascending byte order of their names, so attribution is reproducible.
- A finding whose subtree contains a hard link attributed elsewhere carries the caveat `hard_links_merged`.

## Volume boundary

- At each scan root the walker records `st_dev` in `meta.scope.roots[].st_dev`.
- Descent never enters a directory whose `st_dev` differs from its root's. This matches `find -xdev` in storage-inventory.sh and applies to every walker in every check: disk map roots, categories, and the folder tree; cache folders; artifact discovery and each artifact's sizing walk; duplicate collection, including the `--compare` root, which is bound to its own `st_dev`.
- The mount-point directory itself is not counted; its path is listed in `meta.scope.skipped_mounts`. A skipped mount is a declared exclusion, not a coverage gap.
- Symlinks are never followed below a root. Decision: a scan root given as a symlink is resolved once with `realpath`; `meta.scope.roots[].given` keeps the argument and `path` the resolved location. The legacy `dupfind` keeps its v1 behavior of skipping a symlinked root.
- `disk map` additionally requires each root to resolve to the data volume (`/System/Volumes/Data`); see WI-DISK-MAP.

## Docker figures

Docker figures are informational. They describe space inside Docker's own storage (on macOS, a virtual disk image such as `Docker.raw`) as Docker accounts for it.

- They are never added to any host filesystem total, never contribute to `measured_allocated_bytes` in disk map reconciliation, and never appear in `logical_bytes`, `allocated_bytes`, or `reclaimable_estimate_bytes`.
- Docker findings carry `logical_bytes: null`, `allocated_bytes: null`, `reclaimable_estimate_bytes: null`, and the caveat `docker_reported_not_host`.
- On the host, the Docker disk image appears once as an ordinary file in disk map (with `see_check: "docker scan"`), measured by its own `lstat` like any other file.

## Limitations

- APFS clones and shared extents: a cloned file reports full `st_blocks` even though its extents are shared with another file. Traversal totals therefore cannot guarantee how much space a removal frees. Every finding with a reclaim estimate carries the caveat `apfs_clone_or_shared_extent`. uv clones `.venv` files from its cache on APFS, so artifact sizes in particular can overstate what removal frees.
- Local snapshots retain blocks of deleted files until the snapshot expires.
- Sparse files (for example `Docker.raw`) have `logical_bytes` far above `allocated_bytes`; such findings carry the caveat `sparse_file`.
- Purgeable space and other users' data are part of `df` used space but outside any declared root; disk map reports them only as part of the reconciliation delta.
- Reading a file updates its access time. This is the one unavoidable side effect of a content read (WI-SAFETY AC-07).

## Caveat vocabulary

| Code | Meaning |
|---|---|
| `apfs_clone_or_shared_extent` | Allocated bytes may be shared; removal may free less. |
| `hard_links_merged` | At least one hard-linked name was attributed once only. |
| `sparse_file` | Logical size exceeds allocated size. |
| `docker_reported_not_host` | Figure comes from Docker and is not part of host totals. |
| `inside_other_scope` | Location is inside another measured scope; reported but not summed. |

## Incomplete coverage

Anything the check could not observe goes to `meta.incomplete_coverage`, one entry per path, never truncated (only the table view truncates). Any entry sets `meta.status` to `partial`; the exit code stays 0.

Entry shape: `path`, `reason`, `errno` (symbolic name or `null`), `operation` (`lstat`, `scandir`, `open`, `read`, `hash`).

| `reason` | Trigger |
|---|---|
| `permission_denied` | `EACCES` from POSIX permissions. |
| `privacy_denied` | `EPERM`. On macOS this is almost always a privacy (TCC) denial, for example `~/Library/Mail`, `~/Library/Messages`, or app containers under `~/Library/Containers`. System Integrity Protection can also return `EPERM`; the entry is the same. |
| `dataless` | `SF_DATALESS` is set in `st_flags` (iCloud or File Provider placeholder). The file is never opened, so no download is triggered. Its lstat values are still counted in metadata-only checks; duplicates excludes it from grouping. |
| `vanished` | `ENOENT` for an entry that was listed a moment earlier. |
| `changed_during_scan` | A duplicates candidate whose size or mtime changed between stages; it is excluded from groups. |
| `read_error` | Any other `OSError` on a read, with its `errno`. |

Privacy consent dialogs: macOS may show a consent dialog to the terminal application when a process first touches a protected location. The dialog is raised by the operating system, not by byte-census, and is outside the CLI's control. byte-census never prompts and never reads stdin; if access is denied, the path is recorded as `privacy_denied`. To cover protected locations, grant the terminal Full Disk Access in System Settings; byte-census does not request or bypass it.

## Cost fields

`meta.cost` reports the work one command performed.

| Field | Type | Definition |
|---|---|---|
| `elapsed_s` | number | One wall-clock measurement from command start to the end of rendering, rounded to milliseconds. Never a sum of per-stage or per-worker times. |
| `content_bytes_read` | integer | Bytes returned by byte-census's own `read` calls on file content (hashing). Directory listings and `lstat` are not content reads. Reading subprocess pipes is not counted here. |
| `entries_visited` | integer | Directory entries examined (each `lstat` or `scandir` entry), including hard-link repeats and entries later excluded. Metadata-only checks therefore report their real work. |
| `subprocess_calls` | integer | Calls made through the runner, successful or not. |
| `subprocess_stdout_bytes` | integer | Bytes captured from subprocess stdout. |
| `subprocess_content_bytes_read` | integer or null | Decision: content read by external commands. `0` when `subprocess_calls` is 0; otherwise `null`, because it cannot be measured from this process. |
| `notes` | object | One key per `null` field, naming why it is null. |

Null semantics: a value that cannot be measured is `null` with a note in `cost.notes`, never `0`. Zero means measured and zero. Counters from multiple processes are summed; `elapsed_s` is not.

---

Last Updated: 2026-11-02
Author: Orlando Bruno
