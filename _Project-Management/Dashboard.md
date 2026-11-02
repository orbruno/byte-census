---
artifact_schema: scrum-generated-view
schema_version: 1.0.0
generated: true
generator: scrum-pm-artifacts
generator_version: 1.3.1
view_id: dashboard
source_fingerprint: sha256:c89b85d8c8a73212ff538fcf79f5625c8be83e61a6b700fde70c97467dbde7c9
---

# Project Management Dashboard - duplicate-finder-cli

## Product Goal

byte-census is a deterministic, read-only command-line tool that measures macOS storage use (Docker, caches, regenerable development artifacts, duplicate files, and a disk map reconciled against df), reports the time and bytes read by each check, and lists cleanup commands ordered by risk without ever executing them, with JSON and table output.

## Overall Progress

- Completed estimated points: 0
- Total included estimated points: 62
- Remaining estimated points: 62
- Estimated progress: 0 / 62 (0%)
- Unestimated active Work Items: 5

## Delivery Summary

- Effective active Work Items: 24
- Completed Work Items: 0
- Excluded Work Items: 0
- Estimated active points: 62
- Completed points: 0
- Unestimated active Work Items: 5
- Estimate coverage: 19/24 active items

## Epic Progress

| Epic | State | Progress | Done / Estimated | Remaining | Unestimated | Active |
|---|---|---:|---:|---:|---:|---:|
| No conditional Epics | - | - | - | - | - | - |

## Effective Active Scope

| ID | Kind | Epic | Title | Priority | Rank | Points | State |
|---|---|---|---|---|---:|---:|---|
| [WI-ADR-PYTHON](Work-Items/WI-ADR-PYTHON__python-implementation-decision.md) | decision | - | Record Python as the implementation language for byte-census | A | 1 | 1 | in_progress |
| [WI-CONTRACTS](Work-Items/WI-CONTRACTS__observation-contracts-and-parity.md) | decision | - | Define the observation contracts, parity matrix, and ADR-002 adaptations | A | 2 | 5 | in_progress |
| [WI-RENAME](Work-Items/WI-RENAME__rename-package-and-binary.md) | enabler | - | Move to a src layout with byte-census and dupfind entry points | A | 3 | 3 | in_progress |
| [WI-QUALITY](Work-Items/WI-QUALITY__quality-infrastructure.md) | enabler | - | Provide snapshot, coverage, and CI infrastructure | A | 4 | 2 | in_progress |
| [WI-SAFETY](Work-Items/WI-SAFETY__read-only-safety.md) | enabler | - | Enforce the read-only guarantee in code and tests | A | 5 | 5 | in_progress |
| [WI-CORE](Work-Items/WI-CORE__observation-core.md) | enabler | - | Provide the observation model, cost meter, errors, and rendering | A | 6 | 8 | in_progress |
| [WI-SUGGESTIONS](Work-Items/WI-SUGGESTIONS__risk-ordered-suggestions.md) | story | - | Provide the risk-ordered cleanup suggestion catalog | A | 7 | 2 | in_progress |
| [WI-DUPLICATES](Work-Items/WI-DUPLICATES__duplicates-scan.md) | story | - | Find duplicates with size, partial-hash, and full-hash stages | A | 8 | 5 | in_progress |
| [WI-LEGACY-ADAPTER](Work-Items/WI-LEGACY-ADAPTER__dupfind-legacy-adapter.md) | enabler | - | Keep dupfind as a frozen v1 command with safe report output | A | 9 | 2 | in_progress |
| [WI-ARTIFACTS](Work-Items/WI-ARTIFACTS__artifacts-scan.md) | story | - | Report regenerable development artifacts | B | 1 | 3 | in_progress |
| [WI-CACHES](Work-Items/WI-CACHES__caches-scan.md) | story | - | Report the largest user and tool caches | B | 2 | 3 | in_progress |
| [WI-DOCKER](Work-Items/WI-DOCKER__docker-scan.md) | story | - | Report Docker disk usage, images, and stopped containers | B | 3 | 3 | in_progress |
| [WI-DISK-MAP](Work-Items/WI-DISK-MAP__disk-map-traversal-and-reconciliation.md) | story | - | Map scan roots and reconcile them against df | B | 4 | 5 | proposed |
| [WI-DISK-MAP-CATEGORIES](Work-Items/WI-DISK-MAP-CATEGORIES__disk-map-categories.md) | story | - | Add macOS categories and system context to the disk map | B | 5 | 3 | proposed |
| [WI-DISK-MAP-TREE](Work-Items/WI-DISK-MAP-TREE__disk-map-tree-and-parity.md) | story | - | Add the folder tree and prove parity with the replaced collector | B | 6 | 3 | proposed |
| [WI-AGENT-DOCS](Work-Items/WI-AGENT-DOCS__agent-documentation.md) | story | - | Document byte-census for agents and people | C | 1 | 3 | proposed |
| [WI-VERIFY](Work-Items/WI-VERIFY__end-to-end-verification.md) | enabler | - | Verify byte-census with a real run and an agent | C | 2 | 2 | proposed |
| [WI-RELEASE](Work-Items/WI-RELEASE__release-2-0-0.md) | enabler | - | Release byte-census 2.0.0 locally and on GitHub | C | 3 | 1 | proposed |
| [WI-PARALLEL-WALK](Work-Items/WI-PARALLEL-WALK__parallel-traversal.md) | enabler | - | Measure and adopt process-parallel traversal if it pays off | D | 1 | 3 | proposed |
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
