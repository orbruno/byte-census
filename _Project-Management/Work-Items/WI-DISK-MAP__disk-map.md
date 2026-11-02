---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-DISK-MAP
work_item_kind: story
profile: full
title: "Map disk usage and reconcile it against df"
parent: null
points: 8
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CACHES
  - WI-DOCKER
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-DISK-MAP - Map disk usage and reconcile it against df

## Outcome

A user sees where the data volume's used space is, including macOS categories, and how much remains unexplained, replacing storage-inventory.sh for the features the parity matrix retains.

## Context and Scope

In scope:

- Disk map, reconciliation, categories, snapshot count, folder tree.

Out of scope:

- Parallel traversal (WI-PARALLEL-WALK) and migration of the storage-audit skill (phase 2).

## Acceptance Criteria

- AC-01: `byte-census disk map --scan-root PATH` (repeatable) reports first-level sizes (`--top`, default 30), large files (`--large-file-min`, default 500 MB), and the macOS categories from the parity matrix unless `--skip-categories`.
- AC-02: Scan roots are canonicalized and must resolve to the data volume (`/System/Volumes/Data`); firmlinked paths such as `/Users` map to their data-volume form; roots on other volumes exit 3.
- AC-03: Overlap is handled in both directions: nested roots and categories inside a root are reported but not summed, and a category that contains a root is not double-counted.
- AC-04: Hard links are deduplicated globally across the whole map; complete totals are computed before display truncation; order is deterministic.
- AC-05: Reconciliation reports a signed delta against `df -k /System/Volumes/Data`; a negative delta is flagged as overcount, not clamped to zero.
- AC-06: The system-volume `df -k /` line, disk info, local snapshot count, and a depth-limited folder tree are reported as the parity matrix specifies.
- AC-07: Traversal is single-process; parallelism is out of scope for this item.

## Dependencies and Risks

- Dependency: WI-CONTRACTS parity matrix decides which script features are retained.
- Risk: APFS firmlink behavior was not verified empirically; the alias fixtures must be checked on a real macOS runner.

## Verification

Required checks:

- Fixture accounting matrix with independently computed expected totals for nested, duplicate, aliased, disjoint, and external-volume roots, categories containing roots, cross-directory hard links, permission failures, and measured totals exceeding df.
- Frozen golden output from storage-inventory.sh on a fixture tree, compared for the features the parity matrix retains.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
