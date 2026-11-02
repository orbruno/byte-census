---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-AGENT-DOCS
work_item_kind: story
profile: compact
title: "Document byte-census for agents and people"
parent: null
points: 3
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-LEGACY-ADAPTER
  - WI-ARTIFACTS
  - WI-CACHES
  - WI-DOCKER
  - WI-DISK-MAP-TREE
design_refs: []
verification_refs:
  - ../../SKILL.md
  - ../../README.md
  - ../../tests/test_readme_help.py
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-AGENT-DOCS - Document byte-census for agents and people

## Outcome

An agent can use byte-census correctly from `--help` alone, and the repository documents match the command surface.

## Acceptance Criteria

- AC-01: A root `SKILL.md` under 2,500 tokens states when to use the CLI, the classify-before-acting rule, and where the classification method lives.
- AC-02: Help text documents that `disk map` is the one command that does not use the `scan` verb.
- AC-03: README and CHANGELOG reflect the new commands and the legacy adapter; the Gemini extension is updated or removed.

## Verification

Required checks:

- SKILL.md token count recorded; README and help reviewed against the command list.

Evidence:

- CI: run 41430472632 green on macos-latest at e354a83 on 2026-11-02; closure reviews at e354a83 READY for implementation, documentation corrected in 8ff6830.
- See [the end-to-end verification record](../../docs/verification/2026-11-02--end-to-end.md) and the commit history on feat/byte-census.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
