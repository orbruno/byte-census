---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-VERIFY
work_item_kind: enabler
profile: compact
title: "Verify byte-census with a real run and an agent"
parent: null
points: 2
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-AGENT-DOCS
design_refs: []
verification_refs:
  - ../../docs/verification/2026-11-02--end-to-end.md
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-VERIFY - Verify byte-census with a real run and an agent

## Outcome

The project has evidence that byte-census replaces the experiment's orchestration.

## Acceptance Criteria

- AC-01: A real run of each of the five commands is recorded with time per check and compared with the 2026-11-01 experiment capture as contextual evidence, with differences explained rather than expected to match.
- AC-02: An agent smoke test completes a three-step task using only `SKILL.md` and `--help`.
- AC-03: The storage-cleanup experiment preview still runs with the legacy adapter.

## Verification

Required checks:

- Verification record linked from this item.

Evidence:

- CI: run 41430472632 green on macos-latest at e354a83 on 2026-11-02; closure reviews at e354a83 READY for implementation, documentation corrected in 8ff6830.
- See [the end-to-end verification record](../../docs/verification/2026-11-02--end-to-end.md) and the commit history on feat/byte-census.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
