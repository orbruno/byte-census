---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-CACHES
work_item_kind: story
profile: compact
title: "Report the largest user and tool caches"
parent: null
points: 3
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CORE
  - WI-SUGGESTIONS
design_refs: []
verification_refs:
  - ../../tests/checks/test_caches.py
  - ../../docs/verification/2026-11-02--end-to-end.md
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-CACHES - Report the largest user and tool caches

## Outcome

A user sees the largest folders in `~/Library/Caches` plus uv, npm, and Homebrew caches located elsewhere.

## Acceptance Criteria

- AC-01: `byte-census caches scan` computes complete totals for every cache folder before truncating the display to `--top` (default 20).
- AC-02: uv and brew cache locations come from the tools through the runner; the npm cache location is resolved by reading `npm_config_cache` and `$HOME/.npmrc` (default `$HOME/.npm`) without running npm, because every npm invocation prunes its debug logs; each location is counted once even when inside `~/Library/Caches`.
- AC-03: A missing tool is reported as unavailable in `meta`, not as an error.
- AC-04: Tool caches carry their catalog suggestions (`uv cache prune`, `brew cleanup`, `npm cache verify`), marked low risk.

## Verification

Required checks:

- Fake-runner and fixture tests pass; JSON snapshot exists.

Evidence:

- CI: run 41430472632 green on macos-latest at e354a83 on 2026-11-02; closure reviews at e354a83 READY for implementation, documentation corrected in 8ff6830.
- Commit 3b9d786: complete totals before --top, uv and brew through the runner, npm resolved from configuration; 41 tests; smoke run 24.95 s over 787,984 entries. Process deviation: tests were written after the code (DOD-01 is met by the same commit, the TDD rule was not). Independent review pending.


---
Last Updated: 2026-11-02
Author: Orlando Bruno
