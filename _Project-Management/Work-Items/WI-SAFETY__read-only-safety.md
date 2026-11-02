---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-SAFETY
work_item_kind: enabler
profile: full
title: "Enforce the read-only guarantee in code and tests"
parent: null
points: 5
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

# WI-SAFETY - Enforce the read-only guarantee in code and tests

## Outcome

The package cannot modify user data or run a non-allowlisted command, and tests prove it.

## Context and Scope

In scope:

- Runner, AST guard, path validation, read policy.

Out of scope:

- Legacy `--output` behavior (WI-LEGACY-ADAPTER).

## Acceptance Criteria

- AC-01: Only the runner module creates processes, with `shell=False`, a timeout on every call, and an allowlist of exact argv prefixes: `docker system df`, `docker images`, `docker ps`, `uv cache dir`, `npm config get cache`, `brew --cache`, `df -k`, `diskutil info`, `tmutil listlocalsnapshots`.
- AC-02: A test rejects any argv outside the allowlist, including `docker system prune` and extra arguments after an allowed prefix where the contract forbids them.
- AC-03: An AST-based guard fails if any module other than the runner calls `subprocess`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, or `asyncio.create_subprocess_*`, and if any module other than the legacy adapter's report writer calls `os.remove`, `os.unlink`, `os.rmdir`, `os.rename`, `os.replace`, `os.truncate`, `os.chmod`, `shutil.rmtree`, `shutil.move`, `Path.unlink`, `Path.write_text`, `Path.write_bytes`, `Path.touch`, or `open` with a write, append, or update mode.
- AC-04: Content reads open files with `O_NOFOLLOW`; symlinks are never followed during traversal.
- AC-05: Path arguments containing null bytes or control characters exit 3; non-directory scan roots exit 3.
- AC-06: A test hashes and scans a fixture tree and asserts its contents and modification times are unchanged; access-time updates from reading are documented as the one unavoidable side effect.

## Dependencies and Risks

- Risk: a string-based guard misses aliased imports; mitigated by resolving import aliases in the AST walk.
- Risk: the guard is necessary but not sufficient; behavior tests remain the primary evidence.

## Verification

Required checks:

- Guard, allowlist, path validation, and unchanged-fixture tests pass.

Evidence:

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
