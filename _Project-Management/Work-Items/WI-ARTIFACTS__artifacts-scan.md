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
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-SAFETY
  - WI-QUALITY
design_refs: []
verification_refs: []
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

## Verification

Required checks:

- Fixture tree test passes; JSON snapshot exists.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
