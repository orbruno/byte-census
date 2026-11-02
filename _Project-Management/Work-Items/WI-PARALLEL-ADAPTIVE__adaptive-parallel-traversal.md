---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-PARALLEL-ADAPTIVE
work_item_kind: enabler
profile: compact
title: "Adopt adaptive parallel traversal behind --jobs"
parent: null
points: 5
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-PARALLEL-WALK
design_refs:
  - ../../docs/benchmarks/2026-11-02-parallel-walk/results.md
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-PARALLEL-ADAPTIVE - Adopt adaptive parallel traversal behind --jobs

## Outcome

Disk map and artifacts scans of large trees run about 2.5 times faster on request, without changing results, by splitting traversal into balanced tasks across processes.

## Acceptance Criteria

- AC-01: `--jobs N` (default 1) on `disk map` and `artifacts scan` splits traversal adaptively (a work queue, or splitting any task over an entry budget), keeps one process below a size threshold, and uses the descriptor-relative fsread walks.
- AC-02: Results are identical to `--jobs 1` on the accounting matrix and snapshot fixtures, with hard links merged globally and attributed in path order.
- AC-03: Only `src/byte_census/parallel_walk.py` may import multiprocessing, named explicitly in the guard allowlist, with a planted test proving multiprocessing elsewhere still fails.
- AC-04: A warm ~/Documents benchmark shows at least 1.5 times speedup with `--jobs 8` and records peak memory.

## Verification

Required checks:

- Full suite at --jobs 1 and 4, guard, benchmark record.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
