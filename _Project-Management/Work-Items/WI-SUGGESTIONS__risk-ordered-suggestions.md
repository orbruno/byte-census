---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-SUGGESTIONS
work_item_kind: story
profile: compact
title: "Provide the risk-ordered cleanup suggestion catalog"
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

# WI-SUGGESTIONS - Provide the risk-ordered cleanup suggestion catalog

## Outcome

An agent or user sees which cleanup commands could apply, ordered by risk, and that every one needs owner authorization, without the CLI ever running them.

## Acceptance Criteria

- AC-01: Each suggestion carries `id`, `command`, `risk` (low, medium, high), `reversible`, `requires_owner_authorization: true`, `reason`, and the finding IDs it relates to.
- AC-02: Suggestions are sorted from low to high risk, then by ID.
- AC-03: The catalog covers the suggestions each check emits; every check item lists the suggestions it attaches.
- AC-04: No suggestion string reaches the runner; a test asserts this.

## Verification

Required checks:

- Catalog, ordering, and isolation tests pass.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
