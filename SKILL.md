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

Findings carry empty classification fields (`status: unknown`, `confidence: low`) because the tool observes and does not judge. Classification is your job. The method (what to check, how to rank, what is safe) is in the macOS storage audit guide in the owner's Library; read it before step 2 if you have access.

## Commands

Run through uv from the repository, or as `byte-census` after `uv tool install --editable .`.

Docker usage as the Docker daemon reports it (exit 4 if Docker is missing or stopped):

    byte-census docker scan

Largest caches in `~/Library/Caches` plus the uv, npm, and Homebrew caches:

    byte-census caches scan --top 5

Regenerable development folders (`node_modules`, `.venv`, `venv`, `target`) under a root, each with the command that rebuilds it:

    byte-census artifacts scan ~/Projects

Duplicate files under a path, found by size, then a hash of the first 64 KiB, then a full SHA-256:

    byte-census duplicates scan ~/Downloads --min-size 1048576

Where the used space of the data volume is. This is the one command that does not use the `scan` verb. It requires at least one `--scan-root`:

    byte-census disk map --scan-root ~/Library --top 10

`disk map` reads inside privacy-protected folders such as Mail, Messages, and Library containers. macOS may show a permission prompt the first time. A denial is not an error: the path is listed in `incomplete_coverage`. Tell the owner before running it so the prompt is not a surprise.

## Output

- JSON is the default: one object `{"data": ..., "meta": ...}` on stdout. Add `--format table` for a human-readable view of the same data.
- There is no output-file option; redirect stdout if you need a file.
- Errors are a JSON object on stderr with `code` and `exit_code`.

Exit codes:

- 0: success, including a partial result
- 1: internal error
- 2: usage error (bad option or missing argument)
- 3: validation error (a path that is missing, not a directory, or not on the data volume)
- 4: a source the command needs is unavailable (Docker not running, `df` failed)

## Fields to read

- `data.findings`: what was measured. Each has `kind`, `target`, `allocated_bytes` (disk blocks used, the figure for space questions), `logical_bytes` (file length), `reclaimable_estimate_bytes`, `caveats`, and `suggestion_ids`.
- `data.suggestions`: text proposals. Every one has `requires_owner_authorization: true`. In `disk map` the list is always empty.
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
