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
status: in_progress
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: []
design_refs: []
verification_refs:
  - ../../docs/adr/ADR-001__fw__python-implementation-language.md
  - ../../docs/benchmarks/2026-11-02-traversal/results.md
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
- AC-02: The record cites the committed benchmark in `docs/benchmarks/2026-11-02-traversal/`: in the equal-work run all methods agree on 8,286,834,688 bytes and 351,947 entries, and Python with 10 processes takes 3.1 s warm against 5.1 s for one process, matching Rust with 10 threads (3.4 s, exploratory run); Python threads gain nothing.
- AC-03: The record states the condition that documentation quality matches the playbook baseline (ADR-002 contracts, framework-generated help, SKILL.md).
- AC-04: The record states a revisit trigger: reconsider Rust if WI-PARALLEL-WALK cannot reach its target or traversal time becomes the main complaint.

## Verification

Required checks:

- Decision record exists under `docs/adr/` and is linked from this item; benchmark files are committed.

Evidence:

- Decision record: [ADR-001](../../docs/adr/ADR-001__fw__python-implementation-language.md), written 2026-11-02; AC-01 sections 2 and 4, AC-02 section 3, AC-03 section 4 Condition, AC-04 section 6.
- Benchmark: [results](../../docs/benchmarks/2026-11-02-traversal/results.md) with scripts beside it.
- Independent review: pending.
- Closure: held open until the first CI run with the coverage gate and guard is green (Product Backlog ordering rationale).

---
Last Updated: 2026-11-02
Author: Orlando Bruno
