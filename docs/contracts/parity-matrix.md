# Parity Matrix

Author: Orlando Bruno
Contract version: 1.0.0
Satisfies: WI-CONTRACTS AC-09; consumed by WI-DISK-MAP, WI-DISK-MAP-CATEGORIES, WI-DISK-MAP-TREE, WI-CACHES, WI-ARTIFACTS, WI-DOCKER, WI-DUPLICATES

Sources compared (private documents, cited by name):

- storage-inventory.sh: the read-only macOS storage collector of the Personal Digital Operations project.
- build_preview.py: the storage-cleanup experiment preview of the cognitive-harness project.

Disposition: `retain` keeps the behavior; `change` keeps the purpose with a different, stated behavior; `defer` leaves it out of 2.0.0 with an owner.

## storage-inventory.sh

| # | Observable feature | Disposition | byte-census behavior |
|---|---|---|---|
| S1 | `--scan-root PATH`, repeatable | retain | `disk map --scan-root PATH`, repeatable. |
| S2 | At least one `--scan-root` required (exit 2 without) | retain | `--scan-root` is required and repeatable; a missing option exits 2. Orchestrator decision 2026-11-02: no default traversal, matching the storage audit rule that scope is always declared; the caller passes its own default. |
| S3 | Scan root must be an existing directory (exit 2) | change | Exit 3 (validation), per WI-SAFETY AC-06. |
| S4 | Unknown option exits 2 with usage on stderr | change | Exit 2 with a JSON error on stderr. |
| S5 | `--help`, `-h` | retain | Framework-generated help, starts with `Usage:` and has an `Example:` block. |
| S6 | `--top N`, default 30 first-level entries per root | retain | `--top`, default 30; complete totals computed before truncation. |
| S7 | `--large-file-min MB`, default 500 | retain | `--large-file-min`, default 500 MiB, compared with `logical_bytes` like `find -size`. |
| S8 | Large files: top 20 per root, `find -xdev -type f -size +NM` | retain | Top 20 per root, `logical_bytes` descending, same volume boundary. |
| S9 | Large-file sweep suppresses permission errors | change | Errors go to `incomplete_coverage`. |
| S10 | `--skip-categories` | retain | Same flag and meaning. |
| S11 | `--output DIR` writing `.md` record and `.tsv` inventory | change | No `--output`; one JSON document on stdout, table opt-in. Users redirect stdout. TSV dropped. |
| S12 | `--sample-output` illustrative record | change | Replaced by the committed examples in `docs/contracts/examples/`. |
| S13 | Data-volume baseline: `df -k /System/Volumes/Data` used, total, available | retain | `data.system.df_data_volume` in bytes; the reconciliation baseline. |
| S14 | System-volume line: `df -k /` used | retain | `data.system.df_system_volume.used_bytes`. |
| S15 | `diskutil info /`: Volume Name, File System Personality, Container Total Space, Container Free Space | retain | Same four fields in `data.system.diskutil`; values kept as strings. |
| S16 | Scan root total and first-level sizes via `du -d 1 -k` | change | Own walker: allocated bytes, global hard-link identity, no crossing of `st_dev` (`du` without `-x` crossed mounts). |
| S17 | Per-root count of unreadable entries | change | One `incomplete_coverage` entry per path with reason and errno. |
| S18 | Nested scan root reported but excluded from the sum | retain | `details.nested: true`, `counted: false`. |
| S19 | Category list: User caches, Application support, App containers, Group containers, Developer data, Device backups (MobileSync, inside Application support), Mail, Messages, Downloads, Applications | retain | Same ten categories and labels, measured unless `--skip-categories`. |
| S20 | Category inside a scan root shown but not summed | retain | `counted: false`, caveat `inside_other_scope`. |
| S21 | Category nesting only hard-coded for MobileSync | change | Overlap detected in both directions for every category and root (WI-DISK-MAP-CATEGORIES AC-01). |
| S22 | Local snapshot count: lines containing `com.apple` from `tmutil listlocalsnapshots /` | retain | `data.system.local_snapshot_count`, same counting rule; sizes not attributed. |
| S23 | Docker availability: no CLI, daemon unreachable, or `docker system df` text | change | Disk map: informational `data.system.docker_informational` from `docker system df --format {{json .}}`, never summed. Full detail in `docker scan`. |
| S24 | Tool caches uv, npm, brew via their own commands; only absolute existing paths | retain | Same three commands from the argv table; same path checks. |
| S25 | Tool cache inside `~/Library/Caches` or a scan root counted once | retain | Counted once, reusing the caches measurement (WI-DISK-MAP-CATEGORIES AC-02). |
| S26 | Reconciliation: measured = scan roots + counted categories; remainder clamped to 0 when negative | change | Signed `delta_bytes`; a negative delta sets `overcount: true` and is never clamped. |
| S27 | Incomplete Coverage section | retain | `meta.incomplete_coverage`; `status: partial`. |
| S28 | Decision Queue empty by design | retain | `suggestions: []` in disk map; `see_check` points to the check that owns the location. |
| S29 | Human units (`kb_human`) in output | change | Integer bytes in JSON; human units only in table output. |
| S30 | Local timestamp without zone | change | `captured_at` in RFC 3339 UTC. |
| S31 | Output references the record schema by absolute path | change | Mapping documented in [record-mapping.md](record-mapping.md); no private path in output. |
| S32 | Unavailable sources (docker missing, diskutil empty, tool missing) silently skipped or noted in text | change | `meta.unavailable_sources` with a reason. |

## build_preview.py

| # | Observable feature | Disposition | byte-census behavior |
|---|---|---|---|
| P1 | Docker: `available` flag with a reason when CLI missing or daemon down | change | `docker scan` exits 4 with a JSON error that says how to fix it; English messages. |
| P2 | Docker: per-type rows from `docker system df --format {{json .}}` | retain | `docker_type` findings with Docker-reported bytes and raw strings. |
| P3 | Docker: dangling image count via `docker images -f dangling=true -q` | retain | `summary.dangling_image_count`. |
| P4 | Docker: stopped containers count and a sample of 25 (name, image, status) | change | Full sorted list in `data.stopped_containers`, plus count. |
| P5 | Docker: image inventory (repository, tag, size, `CreatedSince`) | change | Repository, tag, image ID, size in bytes and raw, and absolute `created_at` instead of the relative `CreatedSince`, for determinism. |
| P6 | Caches: children of `~/Library/Caches` (directories, not symlinks), sized with `du -sk` | change | Own walker with allocated bytes and volume boundary; unreadable entries reported instead of counted as 0. |
| P7 | Caches: uv, npm, brew locations added when outside `~/Library/Caches` | retain | Same rule; counted once (WI-CACHES AC-02). |
| P8 | Caches: sorted descending, top 20 | retain | `--top`, default 20, after complete totals. |
| P9 | Artifacts: `node_modules`, `.venv`, `venv`, `target` beside `Cargo.toml`; skip `.git`, `Library`, `.Trash`, symlinks; do not descend into found artifacts | retain | Same rules (WI-ARTIFACTS AC-01, AC-02). |
| P10 | Artifacts: regeneration commands `npm install`, `uv sync`, `cargo build` | retain | `details.regenerate_command` and the `artifact-remove-regenerate` suggestion. |
| P11 | Artifacts: `projectModified` in epoch milliseconds | change | `details.project_mtime` in RFC 3339 UTC. |
| P12 | Artifacts: default root `~/Documents` | change | `artifacts scan ROOT` takes the root as an argument; the caller passes its default. |
| P13 | Duplicates: `dupfind ROOT --format json --output FILE --min-size 1048576 --quiet`, default root `~/Downloads` | change | `duplicates scan PATH --min-size N` on stdout; `dupfind` stays as the frozen adapter until WI-PREVIEW-CALLER. |
| P14 | Folder tree: `du -k -d 4` on the first scan root, folders of at least 100 MiB, children sorted by size, `errors` = stderr line count | change | `data.tree` with depth 4 and minimum 100 MiB as defaults (Decision: flags `--tree-depth` and `--tree-min-mb`); built for every scan root; errors per path in `incomplete_coverage`. |
| P15 | Collector run with `--top 40` and TSV parsing | change | Replaced by `disk map` JSON; the caller passes `--top 40` if it wants it. |
| P16 | Per-step cost: seconds, status, error, and `total_s` | change | Per-command `meta.cost` (elapsed, bytes read, entries, subprocess counters) and `meta.status`; totals across commands belong to the caller. |
| P17 | `capturedAt` in epoch milliseconds | change | `captured_at` in RFC 3339 UTC. |
| P18 | `scope` object recording roots and thresholds | retain | `meta.scope.roots` and `meta.scope.options`. |
| P19 | camelCase keys | change | snake_case keys (ADR-002 naming). |
| P20 | Spanish labels and reasons | change | English. |
| P21 | Timeouts: 1800 s for `du` and collector, 120 s for Docker, 60 s for tool queries | change | No `du` or collector; runner timeouts per the argv table (120 s Docker, 60 s others). |
| P22 | HTML preview rendering (`index.html`, mode 600) | defer | Stays in the experiment; WI-PREVIEW-CALLER moves it onto byte-census JSON. |
| P23 | Unavailable sources: caches folder missing returns an empty list; tool absent skipped | change | Empty findings with `unavailable_sources` entries where a source was expected. |

## Golden parity

WI-DISK-MAP-TREE checks the `retain` rows of storage-inventory.sh against committed golden output produced once from a fixture tree, normalized as that item states. Automated tests never execute storage-inventory.sh.

---

Last Updated: 2026-11-02
Author: Orlando Bruno
