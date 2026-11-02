---
artifact_schema: scrum-generated-view
schema_version: 1.0.0
generated: true
generator: scrum-pm-artifacts
generator_version: 1.3.1
view_id: dashboard
source_fingerprint: sha256:d8ebc6b6b9a524f4d80c2a074f3edf71f9d8085cee7533836e5bc014e0a7620f
---

# Project Management Dashboard - duplicate-finder-cli

## Product Goal

byte-census is a deterministic, read-only command-line tool that measures macOS storage use (Docker, caches, regenerable development artifacts, duplicate files, and a disk map reconciled against df), reports the time and bytes read by each check, and lists cleanup commands ordered by risk without ever executing them, with JSON and table output.

## Overall Progress

- Completed estimated points: 58
- Total included estimated points: 65
- Remaining estimated points: 7
- Estimated progress: 58 / 65 (89%)
- Unestimated active Work Items: 5

## Delivery Summary

- Effective active Work Items: 8
- Completed Work Items: 17
- Excluded Work Items: 0
- Estimated active points: 7
- Completed points: 58
- Unestimated active Work Items: 5
- Estimate coverage: 3/8 active items

## Epic Progress

| Epic | State | Progress | Done / Estimated | Remaining | Unestimated | Active |
|---|---|---:|---:|---:|---:|---:|
| No conditional Epics | - | - | - | - | - | - |

## Effective Active Scope

| ID | Kind | Epic | Title | Priority | Rank | Points | State |
|---|---|---|---|---|---:|---:|---|
| [WI-RELEASE](Work-Items/WI-RELEASE__release-2-0-0.md) | enabler | - | Release byte-census 2.0.0 locally and on GitHub | C | 3 | 1 | proposed |
| [WI-PARALLEL-WALK](Work-Items/WI-PARALLEL-WALK__parallel-traversal.md) | enabler | - | Measure and adopt process-parallel traversal if it pays off | D | 1 | 3 | proposed |
| [WI-FSREAD-SPLIT](Work-Items/WI-FSREAD-SPLIT__split-fsread-and-drop-anchored-path.md) | enabler | - | Split fsread into focused modules and drop AnchoredPath | D | 2 | 3 | proposed |
| [WI-SKILL-ABSORB](Work-Items/WI-SKILL-ABSORB__absorb-storage-audit-skill.md) | enabler | - | Absorb the storage-audit skill into the byte-census SKILL.md | E | 1 | null | proposed |
| [WI-ARCHIVE-INVENTORY](Work-Items/WI-ARCHIVE-INVENTORY__archive-storage-inventory-script.md) | enabler | - | Archive storage-inventory.sh and update SPEC-002 | E | 2 | null | proposed |
| [WI-SYSTEM-CONTEXT](Work-Items/WI-SYSTEM-CONTEXT__system-context-route.md) | enabler | - | Route storage work to byte-census in the system context | E | 3 | null | proposed |
| [WI-PREVIEW-CALLER](Work-Items/WI-PREVIEW-CALLER__experiment-preview-caller.md) | enabler | - | Make the storage-cleanup experiment call byte-census | E | 4 | null | proposed |
| [WI-LEGACY-REMOVAL](Work-Items/WI-LEGACY-REMOVAL__remove-dupfind-adapter.md) | enabler | - | Remove the dupfind adapter in 3.0.0 | E | 5 | null | proposed |

## Excluded and Inconsistent Scope

| ID | Kind | Epic | Stored state | Effective classification |
|---|---|---|---|---|
| - | - | - | - | No excluded work |

Inconsistent active descendants under terminal ancestors: 0

## Evaluation Health

| Definition | Trigger | Result | Verdict | Enforcement | Effective health |
|---|---|---|---|---|---|
| pm-conformance | pm-validate | - | not_run | advisory | missing |

## Learning Follow-up

Captured or validated learnings needing attention: 0
