---
name: byte-census
description: Read-only macOS storage census. Use to find where disk space went, audit storage, or list cleanup candidates (caches, node_modules, Docker, duplicates). It observes and suggests; it never deletes.
---

# byte-census

Author: Orlando Bruno

byte-census measures bytes on a macOS disk and reports what it found as JSON. It changes nothing on the machine.

## When to use it

- The disk is full and you need to know where the space is.
- You are auditing storage or preparing a cleanup list.
- You need candidates: regenerable folders, large caches, Docker usage, duplicate files.

Do not use it to delete, move, or tidy anything. It cannot.

## The rule that matters

Every command is read-only. Any cleanup suggestion in the output is text. Never run a suggested command without the owner's explicit authorization. Work in this order:

1. Observe: run the commands below.
2. Classify: for each finding decide what it is, who owns it, whether it can be regenerated, and how risky removal is.
3. Ask: present the classified list to the owner and wait for approval of specific items.

Findings carry empty classification fields (see Fields to read) because the tool observes and does not judge. Classification is your job. To classify a finding, answer four questions and write the answers in your report:

- What is it (cache, build output, project data, personal files, system component)?
- Who owns it (a tool, a project, the owner)?
- Can it be regenerated or restored, and how (a command, a download, a backup, not at all)?
- What happens if it is wrong (nothing, a rebuild, lost work)? Rank by this, not by size.

Then list the candidates with this classification and the suggestion's `risk`, and wait for the owner to approve specific items. The macOS storage audit guide in the owner's Library covers the method in depth; it is optional further reading and may not be available to you.

## Commands

Run through uv from the repository, or as `byte-census` after `uv tool install --editable .`.

Docker usage as the Docker daemon reports it (exit 4 if Docker is missing or stopped):

    byte-census docker scan

Largest caches in `~/Library/Caches` plus the uv, npm, and Homebrew caches:

    byte-census caches scan --top 5

Options: `--top`.

Regenerable development folders (`node_modules`, `.venv`, `venv`, `target`) under a root, each with the command that rebuilds it:

    byte-census artifacts scan ~/Projects

The suggestion chains three steps: `rm -rf` of the folder, `cd` into the project, then the regeneration command. Running it deletes the folder and also rebuilds it, which downloads packages and takes time.

Duplicate files under a path, found by size, then a hash of the first 64 KiB, then a full SHA-256:

    byte-census duplicates scan ~/Downloads --min-size 1048576

Options: `--compare PATH` (report only content found under both paths), `--min-size BYTES`, `--no-recursive`. The scan includes files inside `node_modules`, `.venv`, and similar folders; that is by design, and the scan root controls the scope. Scan a project folder and you will see its dependency copies; scan `~/Documents` or `~/Downloads` to avoid them.

Where the used space of the data volume is. This is the one command that does not use the `scan` verb. It requires at least one `--scan-root`:

    byte-census disk map --scan-root ~/Library --top 10

Options: `--scan-root` (repeatable), `--top`, `--large-file-min MB`, `--skip-categories`, `--tree-depth`, `--tree-min-mb`.

`disk map` reads inside privacy-protected folders such as Mail, Messages, and Library containers. macOS may show a permission prompt the first time. A denial is not an error: the path is listed in `incomplete_coverage`. Tell the owner before running it so the prompt is not a surprise.

## Output

- JSON is the default: one object `{"data": ..., "meta": ...}` on stdout. Every command takes `--format json|table`; `table` is the human-readable view of the same data. Run `<command> --help` for all options and their defaults.
- There is no output-file option; redirect stdout if you need a file.
- Errors are a JSON object on stderr with `code` and `exit_code`.

Exit codes:

- 0: success, including a partial result
- 1: internal error
- 2: usage error (bad option or missing argument)
- 3: validation error (a path that is missing, not a directory, or not on the data volume)
- 4: a source the command needs is unavailable (Docker not running, `df` failed)

## Fields to read

- `data.findings`: what was measured. Each has `kind`, `target`, `allocated_bytes` (disk blocks used, the figure for space questions), `logical_bytes` (file length), `reclaimable_estimate_bytes`, `caveats`, `suggestion_ids`, and `classification`.
- In a `duplicate_group` finding, `logical_bytes` and `allocated_bytes` are sums over the whole group. `details.file_logical_bytes` and each `details.files[].allocated_bytes` are per file or copy.
- `reclaimable_estimate_bytes`: an upper-bound estimate of the allocated space that acting on the finding could free. Never a promise: APFS clones and shared extents (uv clones `.venv` files from its cache) can make it an overstatement. For duplicates it is every copy except the kept one; for artifacts and caches it is the whole folder; it is null for Docker and `disk map`.
- Caveats on a finding:
  - `apfs_clone_or_shared_extent`: allocated bytes may be shared, so removal may free less.
  - `hard_links_merged`: a file with several names was counted once.
  - `sparse_file`: logical size is above allocated size (for example `Docker.raw`).
  - `docker_reported_not_host`: the figure comes from Docker and is not part of host totals.
- `classification`: `owner` (set only when directly observed, else empty), `status`, `recovery`, `confidence`, `disposition`. byte-census does not classify, so it always emits the defaults `status: unknown` (current state of the item), `recovery: unknown` (whether and how it can be restored), `confidence: low` (how sure the classification is), `disposition: investigate` (what to do next). Treat them as placeholders and give your own values in your report.
- `data.suggestions`: text proposals. Each has `command`, `reason`, and `finding_ids`, and `requires_owner_authorization: true` (always). In `disk map` the list is always empty.
- Suggestion `risk`: `low` is a tool's own safe housekeeping (`uv cache prune`, `brew cleanup`, `docker image prune`); `medium` removes something that can be rebuilt but costs time or interrupts work (`artifact-remove-regenerate`, `docker container prune`); `high` removes content that may not be recoverable (`docker system prune -a`, `docker volume prune`, duplicate removal).
- Suggestion `reversible`: true only if the effect can be undone exactly. Regenerable is not reversible.
- Duplicate suggestion: it keeps the copy whose primary name sorts first by code point and removes every name of the others. That choice is arbitrary, and the owner decides which copy to keep; ask before proposing anything.
- `meta.incomplete_coverage`: paths that could not be read, each with a reason (permission, privacy denial, dataless cloud file). A total with gaps is a lower bound.
- `meta.status`: `complete` or `partial`. `partial` means coverage is incomplete or an optional source failed. It still exits 0, so check this field yourself and say so in your report.
- `see_check` (in `disk map`): names another command that covers the same location in more detail. Follow it instead of guessing.
- `meta.unavailable_sources`: optional tools that were missing or failed (for example Docker).
- Docker figures are what Docker reports. They are never added to host totals.
- `disk map` reconciles its total against `df` as a signed `delta_bytes`. Overlapping scopes are shown but counted once; trust `reconciliation.contributions` for sums.

## Legacy: dupfind

`dupfind` is the original duplicate finder, kept for compatibility. It is deprecated and frozen: its behavior and its unversioned JSON will not change, and it has CSV output and an `--output` option that byte-census lacks. Use `byte-census duplicates scan` for new work.

## Reporting back

State which commands you ran, the `meta.status` of each, any `incomplete_coverage`, the largest findings by `allocated_bytes`, and your classification. Propose actions as a list for approval. Do not execute them.
