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
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-DISK-MAP-TREE
design_refs: []
verification_refs:
  - ../../docs/benchmarks/2026-11-02-parallel-walk/results.md
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
- AC-02: Parallelism is adopted only if it is at least 1.5 times faster and the accounting matrix still passes, with hard links merged globally and attributed deterministically across workers; the module that uses `multiprocessing` is named in the WI-SAFETY guard allowlist.
- AC-03: Otherwise the item closes with the benchmark recorded and no code change.

## Verification

Required checks:

- Benchmark record linked from this item.

Evidence:

- [Benchmark results](../../docs/benchmarks/2026-11-02-parallel-walk/results.md), 2026-11-02, warm ~/Documents (about 2.29 million entries), median of three runs: single 80.46 s; one process per first-level child 1.03 to 1.07 times faster (fails AC-02's 1.5 times); an eight-worker split at depth three 2.56 times faster (30.34 s). Entries, allocated bytes, linked inodes and errors agree exactly on static trees in every mode.
- Decision (AC-03): no production change in this item. The per-child design specified here does not pay off; adaptive splitting does, and is scheduled as WI-PARALLEL-ADAPTIVE. The ADR-001 Rust revisit trigger is not met, because Python processes reach the target.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
