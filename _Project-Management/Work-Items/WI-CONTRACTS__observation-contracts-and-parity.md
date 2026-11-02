---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-CONTRACTS
work_item_kind: decision
profile: compact
title: "Define the observation contracts, parity matrix, and ADR-002 adaptations"
parent: null
points: 5
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-ADR-PYTHON
design_refs: []
verification_refs:
  - ../../docs/contracts/README.md
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-CONTRACTS - Define the observation contracts, parity matrix, and ADR-002 adaptations

## Outcome

Implementation starts from written contracts, so checks report comparable quantities, consumers can rely on schemas, and replaced behavior is preserved or changed on purpose.

## Acceptance Criteria

- AC-01: A quantity glossary defines `logical_bytes` (st_size), `allocated_bytes` (st_blocks x 512), and `reclaimable_estimate_bytes`, all in bytes, with hard-link identity `(st_dev, st_ino)` deduplicated across the whole check, directory blocks counted, and a stated limitation that APFS clones and shared extents prevent traversal totals from guaranteeing reclaimed space.
- AC-02: Docker figures are defined as informational and never added to host filesystem totals.
- AC-03: A versioned JSON example exists for each of the five checks and for the error object, including finding IDs, suggestion IDs, stable ordering, `status` (`complete` or `partial`), and `incomplete_coverage`.
- AC-04: A mapping table converts a CLI finding into a `personal-digital-operation-record` finding (owner as empty string when unknown, status `unknown`, recovery `unknown`, disposition and confidence defaults); the schema version it maps to is recorded, and validation against that schema is a local check recorded as evidence because the schema is not part of this repository.
- AC-05: Every walker in every check stays on the starting volume: descent never crosses an `st_dev` change, matching `find -xdev` in storage-inventory.sh.
- AC-06: An exact argv table lists every external command with its fixed flags and validated variable operands, including `docker system df --format JSON_TEMPLATE`, `docker images --format JSON_TEMPLATE`, `docker images -f dangling=true -q`, `docker ps -a -f status=exited --format JSON_TEMPLATE`, `uv cache dir`, `npm config get cache`, `brew --cache`, `df -k PATH`, `diskutil info /`, and `tmutil listlocalsnapshots /`, where JSON_TEMPLATE is the Go template that renders each row as one JSON object; nothing else is permitted.
- AC-07: Permission errors, including macOS privacy (TCC) denials such as EPERM on Mail, Messages, or Containers, map to `incomplete_coverage`; an OS consent dialog is documented as outside the CLI's control.
- AC-08: A legacy exit-code matrix for dupfind records 2 for argument misuse (current Click behavior), 1 for operational failure, and 3 for an existing output file, each tied to a legacy test; the exit 3 case is recorded as the one intentional v2 change.
- AC-09: A parity matrix marks each observable feature of storage-inventory.sh and the storage-cleanup experiment preview as retain, change, or defer, covering the system-volume df line, disk info, the category list, local snapshot count, Docker availability and image inventory, tool caches, the depth-limited folder tree, defaults, repeatable roots, the clamped negative remainder, and unavailable sources.
- AC-10: An ADR-002 compliance matrix lists each requirement as met, adapted, or not applicable with rationale, including table and CSV output, unrestricted declared scan roots, `--dry-run` and `--yes` not applicable, `-h`, noninteractive operation, and parse errors as JSON.

## Verification

Required checks:

- Contract documents exist under `docs/contracts/` and are linked from this item.

Evidence:

- [docs/contracts/](../../docs/contracts/README.md), written 2026-11-02: AC-01, AC-02, AC-05, AC-07 in quantities.md; AC-03 envelope.md and examples/ (six JSON files, all parse); AC-04 record-mapping.md (schema pinned by SHA-256); AC-06 argv-allowlist.md; AC-08 legacy-exit-codes.md; AC-09 parity-matrix.md; AC-10 adr-002-compliance.md.
- Orchestrator corrections 2026-11-02: `--scan-root` stays required (no default traversal); dupfind keeps the v1 scanner instead of the new engine, honoring the frozen-adapter decision.
- Independent review: READY (see review history in this item and the 2026-11-02 plan and implementation reviews).
- CI: run 41428758619 green on macos-latest at c27ab00 on 2026-11-02 (ruff, format check, full suite with the 80 percent coverage gate).

---
Last Updated: 2026-11-02
Author: Orlando Bruno
