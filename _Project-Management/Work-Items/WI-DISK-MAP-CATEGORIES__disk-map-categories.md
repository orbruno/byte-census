---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-DISK-MAP-CATEGORIES
work_item_kind: story
profile: compact
title: "Add macOS categories and system context to the disk map"
parent: null
points: 3
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-DISK-MAP
  - WI-CACHES
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-DISK-MAP-CATEGORIES - Add macOS categories and system context to the disk map

## Outcome

The disk map accounts for well-known macOS locations and system state, as the parity matrix retains from storage-inventory.sh.

## Acceptance Criteria

- AC-01: The categories from the parity matrix are measured unless `--skip-categories`; overlap is handled in both directions: a category inside a root and a category containing a root are reported but not double-counted.
- AC-02: Tool caches outside `~/Library/Caches` are counted once, reusing the WI-CACHES measurement.
- AC-03: The system-volume `df -k /` line, `diskutil info /`, and the local snapshot count are reported; Docker usage appears as informational only.
- AC-04: Permission and privacy denials on categories are listed in `incomplete_coverage`.

## Verification

Required checks:

- Fixture and fake-runner tests for categories, overlap in both directions, and unavailable sources pass; JSON snapshot exists.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
