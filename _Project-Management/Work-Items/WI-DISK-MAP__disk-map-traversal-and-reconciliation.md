---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-DISK-MAP
work_item_kind: story
profile: full
title: "Map scan roots and reconcile them against df"
parent: null
points: 5
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CORE
  - WI-SUGGESTIONS
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-DISK-MAP - Map scan roots and reconcile them against df

## Outcome

A user sees where the data volume's used space is under declared roots and how much remains unexplained.

## Context and Scope

In scope:

- Traversal, root canonicalization, reconciliation.

Out of scope:

- Managed categories (WI-DISK-MAP-CATEGORIES), folder tree and parity (WI-DISK-MAP-TREE), parallelism (WI-PARALLEL-WALK).

## Acceptance Criteria

- AC-01: `byte-census disk map --scan-root PATH` (repeatable) reports root totals, first-level sizes (`--top`, default 30), and large files (`--large-file-min`, default 500 MB).
- AC-02: Scan roots are canonicalized and must resolve to the data volume (`/System/Volumes/Data`); firmlinked paths such as `/Users` map to their data-volume form; roots on other volumes exit 3; descent never crosses an `st_dev` change.
- AC-03: Nested roots are reported but not summed; hard links are deduplicated globally; complete totals are computed before display truncation; order is deterministic.
- AC-04: Reconciliation reports a signed delta against `df -k /System/Volumes/Data`; a negative delta is flagged as overcount, not clamped to zero.
- AC-05: Traversal is single-process; parallelism is out of scope.
- AC-06: Disk map is observational and emits no cleanup suggestions: `suggestions` is always an empty list, and a finding whose location another check covers (duplicates, artifacts, caches, Docker) names that check in a `see_check` field; a test asserts both.

## Dependencies and Risks

- Risk: APFS firmlink behavior was not verified empirically; alias fixtures must run on a real macOS runner.

## Verification

Required checks:

- Fixture accounting matrix with independently computed expected totals for nested, duplicate, aliased, disjoint, and external-volume roots, cross-directory hard links, permission failures, and measured totals exceeding df.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
