---
artifact_schema: scrum-definition-of-done
schema_version: 1.0.0
type: definition-of-done
id: definition-of-done
content_version: 0.1.0
effective_from: 2026-11-02
supersedes: null
approved_by_role: Product Owner
updated: 2026-11-02
author: Orlando Bruno
---

# Definition of Done

## Purpose

Shared quality policy for every byte-census Work Item. It applies to code, tests, documentation, and project artifacts in this repository. Item-specific acceptance criteria remain in each Work Item.

## Quality Criteria

- DOD-01: Tests for the change are written before or in the same commit as the implementation, and the full suite passes with `uv run pytest`.
- DOD-02: Line coverage of the package is at least 80 percent, enforced by the coverage gate.
- DOD-03: `uv run ruff check` and `uv run ruff format --check` report no findings.
- DOD-04: The AST read-only guard passes: no write, delete, rename, permission, or process call exists outside the modules the guard allows.
- DOD-05: Every command touched by the change has a normalized JSON snapshot test and a test for each error path and exit code it can produce.
- DOD-06: Every command touched by the change has framework-generated `-h` and `--help` that start with `Usage:` and include an `Example:` block.
- DOD-07: Python commands run only through uv; no pip invocation exists in code, docs, or CI.
- DOD-08: No tracked artifact contains AI attribution or em dashes, and no public PM file cites a private absolute path.
- DOD-09: Files stay at or below 800 lines and functions at or below 50 lines.
- DOD-10: CHANGELOG.md records every user-visible change.
- DOD-11: The macOS CI workflow is green on the commit that closes the item.
- DOD-12: The Work Item's Verification section links the evidence for each acceptance criterion.

## Evidence Requirements

| Criterion | Required evidence | Responsible role |
|---|---|---|
| DOD-01 | Commit history showing tests with or before implementation; passing test run output | Developer |
| DOD-02 | Coverage report from the CI run | Developer |
| DOD-03 | ruff step in the CI run | Developer |
| DOD-04 | Guard test result in the CI run | Developer |
| DOD-05 | Snapshot and error-path test files named in the Work Item | Developer |
| DOD-06 | Help snapshot tests | Developer |
| DOD-07 | Repository search result recorded in the Work Item | Developer |
| DOD-08 | Repository search result recorded in the Work Item | Developer |
| DOD-09 | Size check result recorded in the Work Item | Developer |
| DOD-10 | CHANGELOG.md diff | Developer |
| DOD-11 | Link to the green CI run | Developer |
| DOD-12 | Verification section of the Work Item | Product Owner |

## Change Record

| Version | Effective | Change | Rationale | Supersedes |
|---|---|---|---|---|
| 0.1.0 | 2026-11-02 | First policy | Owner-approved baseline after the 2026-11-02 plan reviews | None |

---

Last Updated: 2026-11-02
Author: Orlando Bruno
