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
status: in_progress
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
- AC-03: `dupfind` keeps its v1 stdout, JSON shape, and exit codes; its help text is updated to start with `Usage:` and an `Example:` block so it meets DOD-06; the nine existing tests move to `tests/legacy/` unchanged in intent and pass.
- AC-04: The v1 report writer moves into `src/byte_census/legacy/report_writer.py`, the only module the WI-SAFETY guard allows to write.
- AC-05: pyproject declares a dev dependency group with pytest, pytest-cov, and ruff, added through `uv add --dev`.

## Verification

Required checks:

- `uv run pytest tests/legacy` passes.
- `uv run byte-census --version` prints 2.0.0.

Evidence:

- Commit 6ed35a6 on feat/byte-census: src layout, `byte-census` group, `dupfind` under `byte_census.legacy`, `legacy/report_writer.py` as the only writer, dev group, CHANGELOG 2.0.0.
- 2026-11-02 test run: `uv run pytest -q` 15 passed (9 legacy, 6 new; new tests failed first); `ruff check` and `ruff format --check` clean.
- 2026-11-02 parity check: v1 and new `dupfind` produce byte-identical stdout and stderr for json, csv and table on a fixture with nested, small and 200 KB duplicates; exit codes match for argument misuse (2).
- Independent review: pending.
- Closure: held open until the first CI run with the coverage gate and guard is green.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
