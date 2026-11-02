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
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-DISK-MAP-CATEGORIES
design_refs: []
verification_refs:
  - ../../tests/checks/test_disk_map_tree.py
  - ../../tests/checks/test_disk_map_parity.py
  - ../../tests/fixtures/parity/PROVENANCE.md
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

- CI: run 41430472632 green on macos-latest at e354a83 on 2026-11-02; closure reviews at e354a83 READY for implementation, documentation corrected in 8ff6830.
- See [the end-to-end verification record](../../docs/verification/2026-11-02--end-to-end.md) and the commit history on feat/byte-census.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
