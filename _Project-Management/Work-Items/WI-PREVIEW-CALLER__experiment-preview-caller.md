---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-PREVIEW-CALLER
work_item_kind: enabler
profile: compact
title: "Make the storage-cleanup experiment call byte-census"
parent: null
points: null
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-RELEASE
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-PREVIEW-CALLER - Make the storage-cleanup experiment call byte-census

## Outcome

The cognitive-harness storage-cleanup experiment uses byte-census instead of dupfind and its own orchestration. Deferred to phase 2.

## Acceptance Criteria

- AC-01: The experiment preview obtains each of the five checks from its byte-census command JSON and no longer calls dupfind.

## Verification

Required checks:

- Not yet executed.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
