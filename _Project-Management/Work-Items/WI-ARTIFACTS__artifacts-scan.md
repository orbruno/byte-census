---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-ARTIFACTS
work_item_kind: story
profile: compact
title: "Report regenerable development artifacts"
parent: null
points: 3
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CORE
  - WI-SUGGESTIONS
design_refs: []
verification_refs:
  - ../../tests/checks/test_artifacts.py
  - ../../docs/verification/2026-11-02--end-to-end.md
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-ARTIFACTS - Report regenerable development artifacts

## Outcome

A user sees regenerable folders with their size and regeneration command.

## Acceptance Criteria

- AC-01: `byte-census artifacts scan ROOT` lists `node_modules`, `.venv`, `venv`, and `target` (only beside `Cargo.toml`) with path, kind, project, `allocated_bytes`, regeneration command, and project modification time.
- AC-02: Discovery does not descend into found artifacts, `.git`, `Library`, `.Trash`, or symlinks; each found artifact is sized by a separate walk of its own subtree.
- AC-03: Unreadable entries are listed in `incomplete_coverage`.
- AC-04: Traversal order is sorted, so hard-link attribution is deterministic; each artifact carries a clone caveat because uv clones `.venv` files from its cache on APFS, so its size can overstate what removal frees.
- AC-05: Each artifact carries the catalog suggestion to remove it with its regeneration command, marked medium risk.

## Verification

Required checks:

- Fixture tree test passes; JSON snapshot exists.

Evidence:

- CI: run 41430472632 green on macos-latest at e354a83 on 2026-11-02; closure reviews at e354a83 READY for implementation, documentation corrected in 8ff6830.
- Commit 32e6a46: pruned discovery with dataless and st_dev checks, per-artifact sizing, fixed regeneration suggestions; 30 tests; smoke run 0.037 s. Independent review pending.


---
Last Updated: 2026-11-02
Author: Orlando Bruno
