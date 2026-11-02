---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-RELEASE
work_item_kind: enabler
profile: compact
title: "Release byte-census 2.0.0 locally and on GitHub"
parent: null
points: 1
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-VERIFY
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-RELEASE - Release byte-census 2.0.0 locally and on GitHub

## Outcome

byte-census is installed from its current path and the repository name matches the product.

## Acceptance Criteria

- AC-01: The GitHub repository is renamed only after explicit owner authorization.
- AC-02: `uv tool install --editable` from the current path provides `byte-census` and `dupfind`.
- AC-03: Tag v2.0.0 exists on the integrated branch.

## Verification

Required checks:

- `byte-census --version` prints 2.0.0 from `~/.local/bin`.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
