---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-DUPLICATES
work_item_kind: story
profile: full
title: "Find duplicates with size, partial-hash, and full-hash stages"
parent: null
points: 5
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CORE
  - WI-SUGGESTIONS
design_refs: []
verification_refs:
  - ../../tests/checks/test_duplicates.py
  - ../../docs/verification/2026-11-02--end-to-end.md
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-DUPLICATES - Find duplicates with size, partial-hash, and full-hash stages

## Outcome

A user finds duplicate files while reading as little content as possible, sees how much was read, and sees space estimates that do not overstate what cleanup frees.

## Context and Scope

In scope:

- Duplicate engine and the `duplicates scan` command.

Out of scope:

- CSV output and `--output`, which exist only in the legacy adapter.

## Acceptance Criteria

- AC-01: `byte-census duplicates scan PATH` groups by size, then hashes the first 64 KB, then computes the full SHA-256 only for partial-hash matches.
- AC-02: Files of 64 KB or less are hashed once, not twice; empty files are excluded.
- AC-03: Hard links to the same `(st_dev, st_ino)` form one entry and never count as waste.
- AC-04: Waste is reported as `reclaimable_estimate_bytes` from allocated blocks, with a clone caveat in each group.
- AC-05: A file that vanishes or changes size or mtime between stages is excluded from groups and listed in `incomplete_coverage`.
- AC-06: `--compare PATH`, `--min-size`, and `--recursive/--no-recursive` are supported; formats are json and table.
- AC-07: `cost.content_bytes_read` equals the bytes read by the hashing stages in a fixture test.
- AC-08: Each duplicate group carries the catalog suggestion for removing extra copies, marked high risk and requiring owner authorization.

## Dependencies and Risks

- Risk: sparse files and clones make allocated sizes differ from logical sizes; covered by fixture expectations and the clone caveat.

## Verification

Required checks:

- Fixture tests for each stage, small files, hard links, changing files, compare mode, and byte accounting pass; JSON snapshot exists.

Evidence:

- CI: run 41430472632 green on macos-latest at e354a83 on 2026-11-02; closure reviews at e354a83 READY for implementation, documentation corrected in 8ff6830.
- Commit 4fde168: three-stage hashing with exact content_bytes_read verified against an os.read spy; 51 tests. Independent review pending.


---
Last Updated: 2026-11-02
Author: Orlando Bruno
