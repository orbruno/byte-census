---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-FSREAD-SPLIT
work_item_kind: enabler
profile: compact
title: "Split fsread into focused modules and drop AnchoredPath"
parent: null
points: 3
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-SAFETY
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-FSREAD-SPLIT - Split fsread into focused modules and drop AnchoredPath

## Outcome

fsread.py (about 750 lines) separates descriptor-opening primitives, traversal and content reading behind its current public facade, and artifact discovery passes the discovery lstat explicitly instead of through the AnchoredPath string subclass, so the read-only code stays easy to review.

## Acceptance Criteria

- AC-01: fsread is split into modules for descriptor primitives, traversal and content reads, each at or below 400 lines, with `byte_census.fsread` re-exporting the current public API.
- AC-02: The Artifact record carries the discovery lstat; AnchoredPath is removed and artifact sizing still fails closed without it.
- AC-03: Outputs and snapshots are unchanged and the AST guard allowlist names the new modules explicitly.

## Verification

Required checks:

- Full suite, guard and snapshots unchanged.

Evidence:

- Not yet executed. Raised by the 2026-11-02 closure reviews as maintainability advice.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
