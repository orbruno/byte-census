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
status: done
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-VERIFY
design_refs: []
verification_refs:
  - ../../CHANGELOG.md
  - ../../pyproject.toml
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

- AC-01: the GitHub repository was renamed to orbruno/byte-census on 2026-11-02 after explicit owner authorization; the old URL redirects, and the local remote and pyproject repository URL were updated (d96d684).
- AC-02: `uv tool install --editable .` from the current path replaced the stale duplicate-finder-cli tool; `~/.local/bin/byte-census --version` prints `byte-census 2.0.0`, and the installed `dupfind` and `byte-census` produce output identical to the locked environment on a fixture (the tool environment resolved rich 15.0.0, the lock pins 14.2.0).
- AC-03: annotated tag v2.0.0 at b984aa1 on feat/byte-census, pushed to origin, after CI run 41431865988 passed on macos-latest. The changelog was consolidated into a dated 2.0.0 section first.
- Not done in this item: merging feat/byte-census into main, which was not part of the authorization.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
