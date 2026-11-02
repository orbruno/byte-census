---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-RENAME
work_item_kind: enabler
profile: compact
title: "Move to a src layout with byte-census and dupfind entry points"
parent: null
points: 3
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-ADR-PYTHON
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-RENAME - Move to a src layout with byte-census and dupfind entry points

## Outcome

The project installs as byte-census 2.0.0 in a src layout, with `dupfind` behavior unchanged, so later work builds on the new structure without breaking the existing consumer.

## Acceptance Criteria

- AC-01: The package lives under `src/byte_census/`; pyproject declares name `byte-census`, version 2.0.0, and entry points `byte-census` and `dupfind`.
- AC-02: `byte-census --version` prints 2.0.0, and bare `byte-census` shows help and exits 0.
- AC-03: `dupfind` keeps its v1 behavior exactly; the nine existing tests move to `tests/legacy/` unchanged in intent and pass.
- AC-04: pyproject declares a dev dependency group with pytest, pytest-cov, and ruff, added through `uv add --dev`.

## Verification

Required checks:

- `uv run pytest tests/legacy` passes.
- `uv run byte-census --version` prints 2.0.0.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
