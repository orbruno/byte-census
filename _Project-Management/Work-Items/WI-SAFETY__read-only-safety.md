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
status: in_progress
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-RENAME
  - WI-CONTRACTS
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

The package cannot modify user data, block on special files, trigger downloads, or run a non-allowlisted command, and tests prove it.

## Context and Scope

In scope:

- Runner, AST guard, path validation, read policy.

Out of scope:

- Legacy `--output` behavior (WI-LEGACY-ADAPTER).

## Acceptance Criteria

- AC-01: Only the runner module creates processes, with `shell=False`, a timeout on every call, and argv matched exactly against the CONTRACTS argv table; any other flag or suffix is rejected.
- AC-02: A test rejects argv outside the table, including `docker system prune`, `docker images --filter` variants not in the table, and extra trailing arguments.
- AC-03: The AST guard is an allowlist: package modules may call only listed filesystem and process functions; `subprocess` and `shutil.which` are allowed only in the runner; write, create, rename, delete, permission, link, timestamp, and xattr operations (including `os.open` with write or create flags, `os.write`, `Path.open` in a write mode, `Path.rename`, `Path.replace`, `Path.chmod`, `Path.mkdir`, `os.mkdir`, `os.link`, `os.symlink`, `os.utime`, and `shutil.copy*`) are allowed only in `legacy/report_writer.py`; `ctypes`, `pty`, `tempfile`, `os.fork`, `os.posix_spawn`, and dynamic `getattr(os, ...)` are forbidden; `multiprocessing` is allowed only in a traversal module named by WI-PARALLEL-WALK; import aliases are resolved; the guard scans the package, not tests.
- AC-04: Content reads `lstat` the path, require a regular file, open it with `O_RDONLY | O_NOFOLLOW | O_NONBLOCK`, and re-check identity with `fstat`; FIFOs, devices, and sockets are skipped.
- AC-05: Dataless files (`SF_DATALESS` in `st_flags`, such as iCloud or File Provider placeholders) are never opened and are listed in `incomplete_coverage`, so no check triggers a download.
- AC-06: Path arguments containing null bytes or control characters exit 3; non-directory scan roots exit 3.
- AC-07: A test hashes and scans a fixture tree and asserts its contents and modification times are unchanged; access-time updates from reading are documented as the one unavoidable side effect.

## Dependencies and Risks

- Risk: a string-based guard misses aliased imports; mitigated by resolving import aliases in the AST walk.
- Risk: the guard is necessary but not sufficient; behavior tests remain the primary evidence.

## Verification

Required checks:

- Guard, allowlist, path validation, and unchanged-fixture tests pass.

Evidence:

- Commits 83666cb, 6f372f7, 1ea1ffd, d687f6f, b678063: runner with exact argv and pinned tools, fsread safe reads, paths, allowlist AST guard. Three security review rounds (BLOCKED, BLOCKED, BLOCKED) drove npm removal, an attribute allowlist and the documented threat model; closing review pending.
- Closure: held open until the first CI run is green.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
