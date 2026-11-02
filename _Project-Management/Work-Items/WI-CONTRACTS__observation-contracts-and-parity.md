---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-CONTRACTS
work_item_kind: decision
profile: compact
title: "Define the observation contracts, parity matrix, and ADR-002 adaptations"
parent: null
points: 3
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-ADR-PYTHON
design_refs: []
verification_refs: []
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
- AC-04: A mapping table converts a CLI finding into a valid `personal-digital-operation-record` finding (owner as empty string when unknown, status `unknown`, recovery `unknown`, disposition and confidence defaults).
- AC-05: A parity matrix marks each observable feature of storage-inventory.sh and the storage-cleanup experiment preview as retain, change, or defer, covering the system-volume df line, disk info, the category list, local snapshot count, Docker availability and image inventory, tool caches, the depth-limited folder tree, defaults, repeatable roots, the clamped negative remainder, and unavailable sources.
- AC-06: An ADR-002 compliance matrix lists each requirement as met, adapted, or not applicable with rationale, including table and CSV output, unrestricted declared scan roots, `--dry-run` and `--yes` not applicable, `-h`, noninteractive operation, and parse errors as JSON.

## Verification

Required checks:

- Contract documents exist under `docs/contracts/` and are linked from this item.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
