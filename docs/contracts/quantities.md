# Quantities, Volume Boundary, and Cost

Author: Orlando Bruno
Contract version: 1.0.0 (see [envelope.md](envelope.md) for the version policy)
Satisfies: WI-CONTRACTS AC-01, AC-02, AC-05, AC-07

Every byte figure in byte-census output is an integer number of bytes. Human units (KB, MB, GB) appear only in `--format table`.

## Glossary

| Field | Definition | Source |
|---|---|---|
| `logical_bytes` | Displayed subtree total of `st_size` over the distinct regular-file inodes a finding covers. Directory and symlink `st_size` values are excluded because they do not describe content. | `lstat` |
| `allocated_bytes` | Displayed subtree total of `st_blocks x 512` over the distinct inodes a finding covers: regular files, directories (each directory's own blocks are counted, as `du` does), symlinks, and special files. | `lstat` |
| `counted_allocated_bytes` | Unique counted contribution: the allocated bytes of the inodes this finding claims first under the attribution precedence. Disk map only, in `details` of reconciliation units and in `reconciliation.contributions`. | Derived |
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

## Hard links, overlap, and attribution

Identity of a file is the pair `(st_dev, st_ino)`. Two quantities are kept apart:

| Quantity | Field | Rule | Sums across findings? |
|---|---|---|---|
| Displayed subtree total | `logical_bytes`, `allocated_bytes` | Every distinct inode inside the finding's own subtree, counted once within that subtree, whatever other findings show. | No. Views may overlap (a first-level folder inside its root, a category inside or around a root, a hard link seen from two folders). |
| Unique counted contribution | `counted_allocated_bytes` | Each inode is claimed once per check invocation, by the first claimant under the precedence below. Later claimants add 0. | Yes. Summary totals and disk map reconciliation are sums of counted contributions, which equal the allocated bytes of the union of all measured scopes. |

The global identity set covers all roots, categories, tool caches, workers (WI-PARALLEL-WALK), and both sides of `--compare`. Every visit still counts in `cost.entries_visited`.

Deterministic traversal: directory entries are visited in ascending byte order of their names, and claimants are processed in the precedence order below, so the same tree always gives the same attribution.

Attribution precedence (disk map):

1. Declared scan roots, in ascending canonical path order. A root nested inside another root is not walked again: its displayed total comes from the enclosing walk and its counted contribution is 0.
2. Managed categories, in catalog order (parity matrix S19). A category equal to or inside a root has counted contribution 0 (`overlap`: `equals_scan_root` or `inside_scan_root`). A category that encloses one or more roots is walked without descending into those roots again; its displayed total is the union of its own entries and the enclosed roots, and its counted contribution is only the inodes not already claimed (`overlap`: `encloses_scan_root`). A category inside an earlier category contributes 0 (`inside_category`).
3. Tool caches, in the order uv, npm, brew. A tool cache inside a root or a category contributes 0.

`details.overlap` is `null` for a scope disjoint from all earlier claimants. First-level folders, large files, and tree nodes are views inside a root and never carry a counted contribution.

Other checks: caches, artifacts, and duplicates findings cover disjoint subtrees (artifact discovery never descends into a found artifact; cache folders are siblings; a tool cache inside `~/Library/Caches` is reported once). Their displayed totals can overlap only through hard links. Precedence is the presentation order of the findings, and summary byte totals are sums of counted contributions, so they never double count. These checks do not expose `counted_allocated_bytes` per finding.

A finding carries the caveat `hard_links_merged` when one of its inodes has another name, inside the finding or in another finding, and was therefore counted once.

## Volume boundary

- At each scan root the walker records `st_dev` in `meta.scope.roots[].st_dev`.
- Descent never enters a directory whose `st_dev` differs from its root's. This matches `find -xdev` in storage-inventory.sh and applies to every walker in every check: disk map roots, categories, and the folder tree; cache folders; artifact discovery and each artifact's sizing walk; duplicate collection, including the `--compare` root, which is bound to its own `st_dev`.
- The mount-point directory itself is not counted; its path is listed in `meta.scope.skipped_mounts`. A skipped mount is a declared exclusion, not a coverage gap.
- Symlinks are never followed below a root. Decision: a scan root given as a symlink is resolved once with `realpath`; `meta.scope.roots[].given` keeps the argument and `path` the resolved location. The legacy `dupfind` keeps its v1 behavior of skipping a symlinked root.
- `disk map` additionally requires each root to resolve to the data volume (`/System/Volumes/Data`); see WI-DISK-MAP.
- Firmlinks: on macOS the user data under `/Users`, `/Applications`, and similar paths lives on the data volume and appears under `/` through firmlinks. A walk that starts at `/` (on the read-only system volume) stops at the `st_dev` change and therefore skips that user data. This is expected, not a gap; disk map requires data-volume roots for this reason.

## Tool cache locations

- uv and brew report their cache locations through the runner (`uv cache dir`, `brew --cache`; see [argv-allowlist.md](argv-allowlist.md)).
- Decision: the npm cache location is resolved by reading configuration, never by running npm, because every npm invocation writes or deletes debug logs and can create the cache directory. `byte_census.toolpaths.npm_cache_location` reads, in order: the `npm_config_cache` environment variable (matched case-insensitively, as npm does); a `cache=` line in `$HOME/.npmrc` (key=value lines, `#` and `;` comments ignored, a leading `~` and `${HOME}` expanded, read through the safe opener with a 1 MiB limit); otherwise the default `$HOME/.npm`. It creates nothing and reports which source decided the location.
- Limitation: global npmrc files (`$PREFIX/etc/npmrc`, the builtin npmrc), project `.npmrc` files, `--userconfig` overrides, and environment substitutions other than `${HOME}` are not consulted. If one of them sets `cache`, byte-census reports a different location than npm would.
- Decision: a tool cache location that resolves to the filesystem root (`/`), the data-volume root (`/System/Volumes/Data`), or the home directory itself is refused and never walked. It is reported in `unavailable_sources` with reason `failed` and a detail that begins `refusing to walk`, so the result is `partial`. This stops a setting such as `cache=/` from turning a cache scan into a scan of the whole volume.
- Decision: when `$HOME/.npmrc` exists but cannot be read (not a regular file, over 1 MiB, permission denied), the npm location falls back to the default and the result names the file in `incomplete_coverage` (operation `read`), so it is `partial`. A finding for that location carries `details.location_uncertain`.
- Decision: measuring and tool association are separate. A tool cache inside a cache folder is measured once, as that folder, which keeps the tool's name, `details.tool_locations`, and its catalog suggestion. A tool cache equal to `~/Library/Caches` is measured as the whole folder, root-level files included. Tools that share a location share one finding and each keeps its suggestion (`details.other_tools`).

## Docker figures

Docker figures are informational. They describe space inside Docker's own storage (on macOS, a virtual disk image such as `Docker.raw`) as Docker accounts for it.

- They are never added to any host filesystem total, never contribute to `measured_allocated_bytes` in disk map reconciliation, and never appear in `logical_bytes`, `allocated_bytes`, or `reclaimable_estimate_bytes`.
- Docker findings carry `logical_bytes: null`, `allocated_bytes: null`, `reclaimable_estimate_bytes: null`, and the caveat `docker_reported_not_host`.
- On the host, the Docker disk image appears once as an ordinary file in disk map (with `see_check: "docker scan"`), measured by its own `lstat` like any other file.

## Read-only guarantee and threat model

byte-census never modifies user data, never runs a command outside the argv allowlist ([argv-allowlist.md](argv-allowlist.md)), and never opens a dataless file. Every walk starts at one directory (a scan root, a disk map category, a tool cache location, or the Caches root) that is opened by its path string with `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` and checked with `fstat` against its own `lstat`. Below that start, no path string is followed: every directory is opened with the same flags relative to its parent's descriptor and checked against the `(st_dev, st_ino)` recorded when it was listed, children are examined with `fstatat` on that descriptor, and an entry that was swapped (for example a directory replaced by a symlink) is recorded as `changed_during_scan` and not walked. This holds for every check's walk, including disk map's pruned walk and artifact discovery, which prune through the same descriptor walk. An artifact is sized by reaching it again from its scan root through an `O_NOFOLLOW` openat chain, on the scan root's device, and only if it is still the directory discovery recorded; duplicate candidates are hashed the same way. Any entry on another device than the start directory, including a regular file, is a skipped mount and is never counted. Its AST guard (`tests/support/read_only_guard.py`) prevents accidental writes, process launches, and downloads by contributors. The guard is defense in depth, not a sandbox against code deliberately written to evade static analysis. The primary evidence for the guarantee is behavior tests: the unchanged-fixture test (contents and modification times stay identical after a scan), the runner rejection tests, and the fsread tests for FIFOs, symlinks, devices, dataless files, and identity changes. Reviews judge the guard against this threat model: a finding is a way ordinary code could write, launch a process, or trigger a download without the guard noticing.

## Limitations

- APFS clones and shared extents: a cloned file reports full `st_blocks` even though its extents are shared with another file. Traversal totals therefore cannot guarantee how much space a removal frees. Every finding with a reclaim estimate carries the caveat `apfs_clone_or_shared_extent`. uv clones `.venv` files from its cache on APFS, so artifact sizes in particular can overstate what removal frees.
- Local snapshots retain blocks of deleted files until the snapshot expires.
- Sparse files (for example `Docker.raw`) have `logical_bytes` far above `allocated_bytes`; such findings carry the caveat `sparse_file`.
- Purgeable space and other users' data are part of `df` used space but outside any declared root; disk map reports them only as part of the reconciliation delta.
- Reading a file updates its access time. This is the one unavoidable side effect of a content read (WI-SAFETY AC-07).
- Known residual risk, walk start directories: the start directory of each walk is reached through its path string, and only its last component is protected by `O_NOFOLLOW`. If an ancestor of a scan root (for example a parent of a disk map category or of a tool cache location) is swapped for a symlink between the moment the start is resolved and the moment it is opened, the walk can start in the redirected directory; the `fstat` check then compares against an `lstat` taken through the same redirected path. Everything below the start is protected as described above. Folders listed in the Caches root and artifact folders found by discovery are not walk starts: each is reached again beneath its scan root through an `O_NOFOLLOW` openat chain and verified against the `lstat` recorded when it was listed, so a swapped Caches root or project folder is reported as `changed_during_scan` and contributes no bytes. Artifact sizing requires the scan root and that `lstat`; there is no path-string fallback.
- Known residual risk, path-based content opens: `fsread.open_regular_file`, `fsread.hash_file`, and `fsread.read_small_file` still open a file by its full path string, with only the last component protected. No content read below a scan root uses them: duplicates and the legacy `dupfind` hash beneath their scan root, and the remaining caller reads `~/.npmrc`, which is not below a scan root. The legacy `calculate_hash` keeps a path-based fallback when it is called without a root.
- Known residual risk, dataless eviction: the dataless check uses the `lstat` result and repeats it on the opened descriptor with `fstat`, for files and for every directory the walker or an openat chain opens; a directory found dataless on its descriptor is never listed and no child is looked up in it. If the system evicts a file or directory to a dataless placeholder between `lstat` and `open`, the `open` itself can trigger a download before the `fstat` check refuses the descriptor. A directory evicted after it was opened and checked can still be materialized by looking up or listing its children while the walk holds its descriptor. The first window (between `lstat` and `open`) is a few system calls wide. The second is not: a directory descriptor stays open while its subtree is walked, so a directory evicted after its check remains exposed for as long as the walk takes. Closing either window would need a kernel-level policy (for example the `IOPOL_MATERIALIZE_DATALESS_FILES` I/O policy), which byte-census does not set because it would require `ctypes`, which the read-only guard forbids.

## Caveat vocabulary

| Code | Meaning |
|---|---|
| `apfs_clone_or_shared_extent` | Allocated bytes may be shared; removal may free less. |
| `hard_links_merged` | An inode with more than one name was counted once, here or in another finding. |
| `sparse_file` | Logical size exceeds allocated size. |
| `docker_reported_not_host` | Figure comes from Docker and is not part of host totals. |
| `inside_other_scope` | Location equals or is inside an earlier claimant; displayed, but its counted contribution is 0. |

## Incomplete coverage

Anything the check could not observe goes to `meta.incomplete_coverage`, one entry per path, never truncated (only the table view truncates). Any entry sets `meta.status` to `partial`; the exit code stays 0.

Entry shape: `path`, `reason`, `errno` (symbolic name or `null`), `operation` (`lstat`, `scandir`, `open`, `read`, `hash`).

| `reason` | Trigger |
|---|---|
| `permission_denied` | `EACCES` from POSIX permissions. |
| `privacy_denied` | `EPERM`. On macOS this is almost always a privacy (TCC) denial, for example `~/Library/Mail`, `~/Library/Messages`, or app containers under `~/Library/Containers`. System Integrity Protection can also return `EPERM`; the entry is the same. |
| `dataless` | `SF_DATALESS` is set in `st_flags` (iCloud or File Provider placeholder). A dataless file is never opened, so no download is triggered. Its lstat values are still counted in metadata-only checks; duplicates excludes it from grouping. A dataless directory is counted from its own lstat and recorded with operation `scandir`, but never listed, because listing it would materialize its contents. |
| `vanished` | `ENOENT` for an entry that was listed a moment earlier. |
| `changed_during_scan` | An entry that no longer matches what the walk recorded: a directory replaced during a walk (for example by a symlink) is not walked; a duplicates candidate whose identity, size, or mtime changed between stages, or that can no longer be reached beneath its scan root without following a symlink, is excluded from groups. |
| `read_error` | Any other `OSError` on a read, with its `errno`. |

Privacy consent dialogs: macOS may show a consent dialog to the terminal application when a process first touches a protected location. The dialog is raised by the operating system, not by byte-census, and is outside the CLI's control. byte-census never prompts and never reads stdin; if access is denied, the path is recorded as `privacy_denied`. To cover protected locations, grant the terminal Full Disk Access in System Settings; byte-census does not request or bypass it.

## Cost fields

`meta.cost` reports the work one command performed.

| Field | Type | Definition |
|---|---|---|
| `elapsed_s` | number | One wall-clock measurement: wall-clock time from the start of the command callback until the envelope is complete, just before serialization; rendering cannot time its own end. Rounded to milliseconds. Never a sum of per-stage or per-worker times. |
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
