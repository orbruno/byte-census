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
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-DISK-MAP
  - WI-CACHES
design_refs: []
verification_refs:
  - ../../tests/checks/test_disk_map_categories.py
  - ../../tests/checks/test_disk_map_system.py
  - ../../docs/verification/2026-11-02--end-to-end.md
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

- CI: run 41430472632 green on macos-latest at e354a83 on 2026-11-02; closure reviews at e354a83 READY for implementation, documentation corrected in 8ff6830.
- See [the end-to-end verification record](../../docs/verification/2026-11-02--end-to-end.md) and the commit history on feat/byte-census.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
