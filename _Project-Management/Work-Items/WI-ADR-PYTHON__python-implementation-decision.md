---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-ADR-PYTHON
work_item_kind: decision
profile: compact
title: "Record Python as the implementation language for byte-census"
parent: null
points: 1
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: []
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-ADR-PYTHON - Record Python as the implementation language for byte-census

## Outcome

The project records why byte-census stays in Python although the CLI Creation playbook (ADR-003) defaults to Rust, so the exception is reviewable instead of implicit.

## Acceptance Criteria

- AC-01: The decision record states the playbook default, the chosen option, and the rejected Rust rewrite.
- AC-02: The record cites the committed benchmark in `docs/benchmarks/2026-11-02-traversal/` (scripts and results): Python 10 processes 3.4 s equals Rust 10 threads 3.4 s and parallel du 3.4 s, while Python threads gain nothing (6.3 s versus 5.8 to 6.2 s single process).
- AC-03: The record states the condition that documentation quality matches the playbook baseline (ADR-002 contracts, framework-generated help, SKILL.md).
- AC-04: The record states a revisit trigger: reconsider Rust if WI-PARALLEL-WALK cannot reach its target or traversal time becomes the main complaint.

## Verification

Required checks:

- Decision record exists under `docs/adr/` and is linked from this item; benchmark files are committed.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
