---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-LEGACY-ADAPTER
work_item_kind: enabler
profile: compact
title: "Keep dupfind as a frozen v1 command with safe report output"
parent: null
points: 2
status: proposed
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-SAFETY
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-LEGACY-ADAPTER - Keep dupfind as a frozen v1 command with safe report output

## Outcome

The existing consumer (the storage-cleanup experiment preview) keeps working while byte-census grows its own engine.

## Acceptance Criteria

- AC-01: `dupfind` keeps the v1 scanner in `byte_census.legacy` (it does not use the new duplicates engine) and renders the v1 JSON shape, CSV, and table output, with table as the default, and follows the CONTRACTS legacy exit-code matrix (2 argument misuse, 1 operational failure, 3 existing output file).
- AC-02: `dupfind` prints a deprecation notice on stderr only; stdout is unchanged.
- AC-03: `--output FILE` creates the file exclusively (`O_EXCL`); an existing file or symlink exits 3 with a suggestion; there is no `--force`.
- AC-04: The legacy tests pass, plus `test_existing_output_file_exits_3_without_overwriting` and `test_output_symlink_exits_3_without_following`.
- AC-05: The adapter is documented for removal in 3.0.0, after WI-PREVIEW-CALLER is done.

## Verification

Required checks:

- `uv run pytest tests/legacy` passes, including the new exclusive-creation tests.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
