---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-PARALLEL-WALK
work_item_kind: enabler
profile: compact
title: "Measure and adopt process-parallel traversal if it pays off"
parent: null
points: 3
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-DISK-MAP
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-PARALLEL-WALK - Measure and adopt process-parallel traversal if it pays off

## Outcome

Disk map runs faster only if measurement on a full scan shows a gain without accounting errors.

## Acceptance Criteria

- AC-01: A benchmark on `~/Documents` compares the single-process walk with a process-per-child walk, cold and warm.
- AC-02: Parallelism is adopted only if it is at least 1.5 times faster and the accounting matrix still passes, with hard links attributed deterministically across workers.
- AC-03: Otherwise the item closes with the benchmark recorded and no code change.

## Verification

Required checks:

- Benchmark record linked from this item.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
