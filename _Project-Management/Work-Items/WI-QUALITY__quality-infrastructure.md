---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-QUALITY
work_item_kind: enabler
profile: compact
title: "Provide snapshot, coverage, and CI infrastructure"
parent: null
points: 2
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CORE
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-QUALITY - Provide snapshot, coverage, and CI infrastructure

## Outcome

Every later check lands with snapshot tests and runs through CI, without retrofitting.

## Acceptance Criteria

- AC-01: A snapshot helper compares JSON output after normalizing volatile fields (`captured_at`, `cost`, absolute fixture roots).
- AC-02: The coverage gate fails the run below 80 percent line coverage.
- AC-03: A GitHub Actions workflow on `macos-latest` runs ruff and the full suite, including legacy tests, on push and pull request.
- AC-04: Per-check snapshot tests are required by the Definition of Done, not by this item.

## Verification

Required checks:

- CI run on the feature branch is green.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
