---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-CORE
work_item_kind: enabler
profile: full
title: "Provide the observation model, cost meter, errors, and rendering"
parent: null
points: 8
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CONTRACTS
  - WI-QUALITY
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

# WI-CORE - Provide the observation model, cost meter, errors, and rendering

## Outcome

Every check reports through one immutable model, one cost meter, one error path, and one renderer, so output stability and failure behavior are defined once.

## Context and Scope

In scope:

- Model, cost meter, error handling, exit codes, JSON and table rendering, common options.

Out of scope:

- Subprocess access, file access policy, and the guard (WI-SAFETY).

## Acceptance Criteria

- AC-01: JSON output uses `{data, meta}` matching the CONTRACTS examples, with `meta.schema_version`, `captured_at`, `scope` (including the measured `st_dev`), `cost`, `status`, and `incomplete_coverage`.
- AC-02: Findings carry the classification fields defined in CONTRACTS from the first release, so later items do not change the finding shape.
- AC-03: `cost.elapsed_s` is one wall-clock measurement from command start until the envelope is complete, before serialization and is never summed; `content_bytes_read` counts bytes returned by the application's own reads; `entries_visited` counts directory entries examined, so metadata-only checks report real work; values that cannot be measured, such as reads inside subprocesses, are null with a note, never zero; counters from multiple processes are summed.
- AC-04: Errors are JSON on stderr with `error`, `reason`, `suggestion`, and `help`; Click usage errors are converted to the same shape.
- AC-05: Exit codes are 0 success (including partial coverage, reported in `meta`), 1 unexpected internal error, 2 argument misuse, 3 validation error, 4 source unavailable.
- AC-06: JSON is the default stdout format; `--format table` renders a table; no ANSI codes appear when stdout is not a TTY or `NO_COLOR` is set.
- AC-07: The CLI never prompts; every option has a flag form.
- AC-08: The snapshot helper from WI-QUALITY is extended to the real envelope: it normalizes `meta.scope.roots[].st_dev` and the path-derived ID fields (`id`, `finding_ids`, `suggestion_ids`) so snapshots are stable across machines.

## Dependencies and Risks

- Dependency: WI-CONTRACTS supplies the schemas this item implements.
- Risk: a shape change after snapshots exist forces a schema version bump; mitigated by implementing classification fields now.

## Verification

Required checks:

- Unit tests for model immutability, cost aggregation, error anatomy, exit-code mapping, TTY and NO_COLOR rendering pass.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
