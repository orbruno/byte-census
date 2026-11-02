# Output Envelope, Findings, Suggestions, Errors, and Exit Codes

Author: Orlando Bruno
Contract version: 1.0.0
Satisfies: WI-CONTRACTS AC-03; supplies the shapes for WI-CORE, WI-SUGGESTIONS, and every check

Examples: [examples/](examples/). Each is valid JSON at `schema_version` 1.0.0.

## Formats and streams

- JSON is the default stdout format. `--format table` is opt-in for people and renders the same data.
- stdout carries the result only; stderr carries errors (JSON) and nothing else in byte-census.
- No ANSI codes when stdout is not a TTY or `NO_COLOR` is set. JSON never contains ANSI codes.
- There is no `--output` option. Users redirect stdout (`byte-census disk map > map.json`). CSV exists only in the legacy `dupfind`.
- The CLI never prompts and never reads stdin.

## Envelope

Every successful command prints one JSON object:

```json
{"data": {...}, "meta": {...}}
```

### `meta`

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Version of this contract, semver. |
| `tool` | object | `name` (`byte-census`) and `version` (package version). |
| `command` | string | `docker scan`, `caches scan`, `artifacts scan`, `duplicates scan`, or `disk map`. |
| `captured_at` | string | Command start, RFC 3339 in UTC with `Z`. |
| `status` | string | `complete` or `partial` (rules below). |
| `scope.roots` | array | One object per root: `path` (resolved), `given` (as typed, or the source such as `uv cache dir`), `st_dev` (measured). Empty for `docker scan`. |
| `scope.options` | object | Effective option values, defaults included. |
| `scope.skipped_mounts` | array | Paths where descent stopped at an `st_dev` change. |
| `cost` | object | See [quantities.md](quantities.md#cost-fields). |
| `incomplete_coverage` | array | See [quantities.md](quantities.md#incomplete-coverage). |
| `unavailable_sources` | array | Optional sources that could not be used: `source`, `reason` (`not_installed`, `not_running`, `failed`, `timed_out`), `detail`. |

Status rules:

- `partial` when `incomplete_coverage` is non-empty, or when any `unavailable_sources` entry has reason `failed` or `timed_out`.
- `complete` otherwise. A tool that is simply not installed (`not_installed`) does not make a result partial: there is nothing of that tool to measure.
- Both statuses exit 0.

### `data`

| Field | Present in | Meaning |
|---|---|---|
| `summary` | all | Check-specific totals; byte totals follow the glossary. |
| `findings` | all | Array of findings, ordered as below. |
| `suggestions` | all | Array of suggestions; always `[]` in `disk map`. |
| `images`, `stopped_containers` | `docker scan` | Image inventory and stopped containers. |
| `reconciliation`, `system`, `tree` | `disk map` | df reconciliation (`df_used_bytes`, `measured_allocated_bytes`, signed `delta_bytes`, `overcount`, and `contributions`: one `{finding_id, counted_allocated_bytes}` per reconciliation unit), system context, folder tree. |

## Finding

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable ID (rules below). |
| `kind` | string | Check-specific kind, for example `duplicate_group`, `artifact`, `cache_dir`, `tool_cache`, `docker_type`, `root_total`, `first_level`, `large_file`, `category`. |
| `target` | string | Absolute path, or a managed-object identifier (`docker:Images`, `sha256:<hex>`). |
| `logical_bytes` | integer or null | See glossary. `null` for Docker findings. |
| `allocated_bytes` | integer or null | See glossary. `null` for Docker findings. |
| `reclaimable_estimate_bytes` | integer or null | See glossary. |
| `caveats` | array of string | Codes from the caveat vocabulary in quantities.md. |
| `see_check` | string or null | Another check that covers this location. Set only by `disk map`; `null` elsewhere. |
| `suggestion_ids` | array of string | IDs of suggestions in `data.suggestions` that relate to this finding, in suggestion order. |
| `classification` | object | `owner`, `status`, `recovery`, `confidence`, `disposition` (below). |
| `details` | object | Kind-specific fields. Disk map reconciliation units (`root_total`, `category`, `tool_cache`) carry `counted_allocated_bytes` and `overlap` (`null`, `equals_scan_root`, `inside_scan_root`, `encloses_scan_root`, `inside_category`); see quantities.md. |

Classification fields exist from 1.0.0 so later items never change the finding shape (WI-CORE AC-02). byte-census observes; it does not classify. Defaults:

| Field | Value |
|---|---|
| `owner` | Decision: set only from direct observation: the project directory for an artifact, the tool name (`uv`, `npm`, `brew`) for a tool cache, `docker` for Docker findings; otherwise `""` (unknown). |
| `status` | `unknown` |
| `recovery` | `unknown` |
| `confidence` | `low` |
| `disposition` | `investigate` |

Values follow the vocabulary of the personal digital operation record; see [record-mapping.md](record-mapping.md).

### Finding IDs

Decision: `id = <prefix>-<first 12 hex of SHA-256 of "<kind>\0<target>">`, with prefixes `dkr` (docker scan), `cch` (caches scan), `art` (artifacts scan), `dup` (duplicates scan), `map` (disk map).

- The same kind and target give the same ID in every run, so IDs survive re-runs and can be referenced from records.
- A duplicate group's target is `sha256:<full content hash>`, so its ID depends on content, not on which paths hold it.

### `see_check` (disk map only)

Disk map emits no suggestions. When a finding's location is covered by another check, it names that check, with this precedence:

1. `docker scan`: inside Docker's data location (for example `~/Library/Containers/com.docker.docker`).
2. `caches scan`: `~/Library/Caches` or a uv, npm, or Homebrew cache location.
3. `artifacts scan`: a path component named `node_modules`, `.venv`, `venv`, or `target` beside `Cargo.toml`.
4. `duplicates scan`: Decision: every `large_file` finding and the `Downloads` folder (as a first-level folder or as a category), because large files and downloads are the main duplicate candidates.

Otherwise `see_check` is `null`.

## Suggestion

Suggestions are text only. No suggestion string ever reaches the runner (WI-SUGGESTIONS AC-04).

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Catalog ID for a check-wide suggestion (`docker-image-prune`), or `<catalog-id>@<finding-id>` for a per-finding suggestion. |
| `command` | string | The command a person could run, shell-quoted. Never executed. |
| `risk` | string | `low`, `medium`, or `high`. |
| `reversible` | boolean | `true` only if the effect can be undone exactly. Regenerable is not reversible. |
| `requires_owner_authorization` | boolean | Always `true`. |
| `reason` | string | Why the suggestion applies and what it removes. |
| `finding_ids` | array of string | Related finding IDs, in `data.findings` order (see Ordering). |

Catalog for 1.0.0:

| Catalog ID | Check | Scope | Command | Risk |
|---|---|---|---|---|
| `docker-image-prune` | docker scan | check-wide | `docker image prune` | low |
| `docker-container-prune` | docker scan | check-wide | `docker container prune` | medium |
| `docker-system-prune-all` | docker scan | check-wide | `docker system prune -a` | high |
| `docker-volume-prune` | docker scan | check-wide | `docker volume prune` | high |
| `uv-cache-prune` | caches scan | check-wide | `uv cache prune` | low |
| `brew-cleanup` | caches scan | check-wide | `brew cleanup` | low |
| `npm-cache-verify` | caches scan | check-wide | `npm cache verify` | low |
| `artifact-remove-regenerate` | artifacts scan | per finding | `rm -rf -- '<artifact>' && cd -- '<project>' && <regenerate>` | medium |
| `duplicate-remove-extra-copies` | duplicates scan | per finding | `rm -- '<path>'` for every name of every copy except the one that sorts first | high |

Decision: a check-wide suggestion is emitted once per run when at least one related finding exists, and lists all related findings. A tool-cache suggestion is emitted only when that tool's cache was found. `docker-system-prune-all` relates to Images, Containers, and Build Cache only: without `--volumes` it removes no volume, so volumes relate only to `docker-volume-prune`.

## Ordering

All arrays are deterministic. Strings compare by Unicode code point. Each array has exactly one presentation rule, stated here and nowhere else. Selection (which items survive `--top` or a fixed limit) is a separate step that runs first, on complete totals, so summaries never depend on truncation.

Selection rules:

| Selection | Key |
|---|---|
| `first_level` per root (`--top`, default 30) | `allocated_bytes` descending, then `target` ascending |
| `large_file` per root (20) | `logical_bytes` descending, then `target` ascending |
| Cache folders (`--top`, default 20) | `allocated_bytes` descending, then `target` ascending |
| Tree nodes (`--tree-depth`, `--tree-min-mb`) | Threshold only; no ranking |

Large files use `logical_bytes` for both selection and presentation because their threshold is `st_size` (like `find -size` in the replaced collector) and a sparse file such as `Docker.raw` is recognized by its logical size. Every other byte ranking uses `allocated_bytes`.

Presentation rules:

| Array | Order |
|---|---|
| `findings` (docker scan) | Docker type order: Images, Containers, Local Volumes, Build Cache. |
| `findings` (caches, artifacts, duplicates) | `allocated_bytes` descending, then `target` ascending. |
| `findings` (disk map) | Kind rank (`root_total`, `first_level`, `large_file`, `category`, `tool_cache`); within a kind, the kind's size key descending (`logical_bytes` for `large_file`, `allocated_bytes` otherwise); then `target` ascending. |
| `suggestions` | Risk (low, medium, high), then `id` ascending. |
| `finding.suggestion_ids` | Order of `data.suggestions`. |
| `suggestion.finding_ids` | Order of `data.findings`. |
| `reconciliation.contributions` (disk map) | Attribution precedence (quantities.md): roots by path, categories in catalog order, tool caches uv, npm, brew. |
| `details.files` (duplicates) | `path` ascending; `hard_link_paths` within a file also `path` ascending. |
| `images` | `docker_reported_size_bytes` descending, then repository, tag, image ID. |
| `stopped_containers` | Name, then container ID. |
| `tree.roots` | `path` ascending. |
| Tree `children` | `allocated_bytes` descending, then `path` ascending. |
| `scope.roots` | `path` ascending; identical resolved roots are merged. |
| `incomplete_coverage` | `path`, then `reason`. |
| `unavailable_sources` | `source`. |

## Error object

Errors are a single JSON object on stderr; stdout is empty.

| Field | Meaning (ADR-002 S-04 anatomy) |
|---|---|
| `schema_version` | Contract version. |
| `error` | What failed. |
| `reason` | Why it failed. |
| `suggestion` | How to fix it. A plain string; unrelated to cleanup suggestions. |
| `help` | Where to get help, usually the `--help` command for the subcommand. |
| `code` | `internal_error`, `usage_error`, `validation_error`, or `source_unavailable`. |
| `exit_code` | Same value as the process exit code. |

Click usage errors are converted to this shape. Example: [examples/error.json](examples/error.json).

## Exit codes

| Code | `code` | Meaning | Examples |
|---|---|---|---|
| 0 | none | Success, including `status: partial`. | Any completed check. |
| 1 | `internal_error` | Unexpected internal error. | Unhandled exception, rendered without traceback. |
| 2 | `usage_error` | Argument misuse detected by the parser. | Unknown option, missing argument, invalid choice, `--top -1`. |
| 3 | `validation_error` | Arguments parse but fail validation. | Path with a null byte or control character; scan root missing or not a directory; disk map root not on the data volume. |
| 4 | `source_unavailable` | A source the command cannot work without is unavailable. | `docker scan` without the Docker CLI or with the daemon down; `disk map` when `df -k /System/Volumes/Data` fails. |

Decision: a missing scan root exits 3, not 2, so path checks run in byte-census's validator instead of Click's `exists=True`. Decision: `disk map` exits 4 when the data-volume `df` fails, because reconciliation is its core result; optional sources (Docker, diskutil, tmutil, tool caches) only add `unavailable_sources` entries.

## Schema version policy

`meta.schema_version` is the contract version, independent from the package version.

- MAJOR: a field removed or renamed, a type or unit changed, the meaning of a value changed, or an ordering rule changed. Requires a package major version (ADR-002 O-06).
- MINOR: a field, finding kind, caveat code, catalog entry, coverage reason, or enum value added. Consumers must ignore unknown fields and tolerate unknown enum values.
- PATCH: documentation clarifications, or a fix that makes output conform to this contract.
- Every example in `examples/` carries the current version; snapshot tests compare against them after normalization (WI-QUALITY).
- The legacy `dupfind` v1 JSON is unversioned and frozen; it is not governed by this policy.

---

Last Updated: 2026-11-02
Author: Orlando Bruno
