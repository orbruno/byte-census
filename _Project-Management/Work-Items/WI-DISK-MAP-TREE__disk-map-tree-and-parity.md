---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-DISK-MAP-TREE
work_item_kind: story
profile: compact
title: "Add the folder tree and prove parity with the replaced collector"
parent: null
points: 3
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-DISK-MAP-CATEGORIES
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-DISK-MAP-TREE - Add the folder tree and prove parity with the replaced collector

## Outcome

The disk map supplies the depth-limited folder tree the experiment preview uses, and evidence shows which collector behavior is preserved.

## Acceptance Criteria

- AC-01: A depth-limited folder tree with a minimum size is reported as the parity matrix specifies.
- AC-02: Parity is checked against committed golden output produced once on a fixture tree (storage-inventory.sh for first-level sizes, large files and categories; the experiment preview's `du -k -d 4` for the folder tree), with provenance recorded and normalized before freezing: home and absolute paths replaced by placeholders, machine-specific df, diskutil, and snapshot values replaced, and em dashes removed.
- AC-03: Automated tests never execute storage-inventory.sh, the experiment preview, or `du`.

## Verification

Required checks:

- Golden parity test passes for the features the parity matrix retains; JSON snapshot exists.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
