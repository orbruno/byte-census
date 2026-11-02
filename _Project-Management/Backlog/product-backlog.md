---
artifact_schema: scrum-product-backlog
schema_version: 1.0.0
type: product-backlog
id: product-backlog
product_goal: "byte-census is a deterministic, read-only command-line tool that measures macOS storage use (Docker, caches, regenerable development artifacts, duplicate files, and a disk map reconciled against df), reports the time and bytes read by each check, and lists cleanup commands ordered by risk without ever executing them, with JSON and table output."
ordered_items:
  - work_item_id: WI-ADR-PYTHON
    priority: A
    rank: 1
  - work_item_id: WI-CONTRACTS
    priority: A
    rank: 2
  - work_item_id: WI-RENAME
    priority: A
    rank: 3
  - work_item_id: WI-QUALITY
    priority: A
    rank: 4
  - work_item_id: WI-SAFETY
    priority: A
    rank: 5
  - work_item_id: WI-CORE
    priority: A
    rank: 6
  - work_item_id: WI-SUGGESTIONS
    priority: A
    rank: 7
  - work_item_id: WI-DUPLICATES
    priority: A
    rank: 8
  - work_item_id: WI-LEGACY-ADAPTER
    priority: A
    rank: 9
  - work_item_id: WI-ARTIFACTS
    priority: B
    rank: 1
  - work_item_id: WI-CACHES
    priority: B
    rank: 2
  - work_item_id: WI-DOCKER
    priority: B
    rank: 3
  - work_item_id: WI-DISK-MAP
    priority: B
    rank: 4
  - work_item_id: WI-DISK-MAP-CATEGORIES
    priority: B
    rank: 5
  - work_item_id: WI-DISK-MAP-TREE
    priority: B
    rank: 6
  - work_item_id: WI-AGENT-DOCS
    priority: C
    rank: 1
  - work_item_id: WI-VERIFY
    priority: C
    rank: 2
  - work_item_id: WI-RELEASE
    priority: C
    rank: 3
  - work_item_id: WI-PARALLEL-WALK
    priority: D
    rank: 1
  - work_item_id: WI-SKILL-ABSORB
    priority: E
    rank: 1
  - work_item_id: WI-ARCHIVE-INVENTORY
    priority: E
    rank: 2
  - work_item_id: WI-SYSTEM-CONTEXT
    priority: E
    rank: 3
  - work_item_id: WI-PREVIEW-CALLER
    priority: E
    rank: 4
  - work_item_id: WI-LEGACY-REMOVAL
    priority: E
    rank: 5
updated: 2026-11-02
author: Orlando Bruno
---

# Product Backlog

## Product Goal

byte-census is a deterministic, read-only command-line tool that measures macOS storage use (Docker, caches, regenerable development artifacts, duplicate files, and a disk map reconciled against df), reports the time and bytes read by each check, and lists cleanup commands ordered by risk without ever executing them, with JSON and table output.

Progress evidence: each of the five checks returns stable JSON and a table, reports its cost, and a real run is comparable with the 2026-11-01 storage-cleanup experiment capture.

## Ordered Backlog

| Rank | Priority | Work Item |
|---:|:---:|---|
| 1 | A | [WI-ADR-PYTHON](../Work-Items/WI-ADR-PYTHON__python-implementation-decision.md) |
| 2 | A | [WI-CONTRACTS](../Work-Items/WI-CONTRACTS__observation-contracts-and-parity.md) |
| 3 | A | [WI-RENAME](../Work-Items/WI-RENAME__rename-package-and-binary.md) |
| 4 | A | [WI-QUALITY](../Work-Items/WI-QUALITY__quality-infrastructure.md) |
| 5 | A | [WI-SAFETY](../Work-Items/WI-SAFETY__read-only-safety.md) |
| 6 | A | [WI-CORE](../Work-Items/WI-CORE__observation-core.md) |
| 7 | A | [WI-SUGGESTIONS](../Work-Items/WI-SUGGESTIONS__risk-ordered-suggestions.md) |
| 8 | A | [WI-DUPLICATES](../Work-Items/WI-DUPLICATES__duplicates-scan.md) |
| 9 | A | [WI-LEGACY-ADAPTER](../Work-Items/WI-LEGACY-ADAPTER__dupfind-legacy-adapter.md) |
| 1 | B | [WI-ARTIFACTS](../Work-Items/WI-ARTIFACTS__artifacts-scan.md) |
| 2 | B | [WI-CACHES](../Work-Items/WI-CACHES__caches-scan.md) |
| 3 | B | [WI-DOCKER](../Work-Items/WI-DOCKER__docker-scan.md) |
| 4 | B | [WI-DISK-MAP](../Work-Items/WI-DISK-MAP__disk-map-traversal-and-reconciliation.md) |
| 5 | B | [WI-DISK-MAP-CATEGORIES](../Work-Items/WI-DISK-MAP-CATEGORIES__disk-map-categories.md) |
| 6 | B | [WI-DISK-MAP-TREE](../Work-Items/WI-DISK-MAP-TREE__disk-map-tree-and-parity.md) |
| 1 | C | [WI-AGENT-DOCS](../Work-Items/WI-AGENT-DOCS__agent-documentation.md) |
| 2 | C | [WI-VERIFY](../Work-Items/WI-VERIFY__end-to-end-verification.md) |
| 3 | C | [WI-RELEASE](../Work-Items/WI-RELEASE__release-2-0-0.md) |
| 1 | D | [WI-PARALLEL-WALK](../Work-Items/WI-PARALLEL-WALK__parallel-traversal.md) |
| 1 | E | [WI-SKILL-ABSORB](../Work-Items/WI-SKILL-ABSORB__absorb-storage-audit-skill.md) |
| 2 | E | [WI-ARCHIVE-INVENTORY](../Work-Items/WI-ARCHIVE-INVENTORY__archive-storage-inventory-script.md) |
| 3 | E | [WI-SYSTEM-CONTEXT](../Work-Items/WI-SYSTEM-CONTEXT__system-context-route.md) |
| 4 | E | [WI-PREVIEW-CALLER](../Work-Items/WI-PREVIEW-CALLER__experiment-preview-caller.md) |
| 5 | E | [WI-LEGACY-REMOVAL](../Work-Items/WI-LEGACY-REMOVAL__remove-dupfind-adapter.md) |

## Ordering Rationale

- Priority A is the shortest usable MVP: the language decision, the observation contracts, the src layout, quality and safety infrastructure, the core, the suggestion catalog, the duplicates check, and the legacy adapter that keeps the current consumer working.
- WI-CONTRACTS precedes code because both 2026-11-02 plan reviews found that quantities, schemas, argv templates, and parity were undefined; implementing first would force schema changes after snapshots exist.
- WI-QUALITY and WI-SAFETY come right after WI-RENAME so the Definition of Done 0.1.0 gates (coverage, CI, guard) exist early. Integration sequence: WI-ADR-PYTHON, WI-CONTRACTS, and WI-RENAME stay open until the first CI run with the coverage gate and the guard is green, then close together; the Definition of Done is not changed.
- WI-SUGGESTIONS precedes every check so each check attaches its suggestions when it is built.
- WI-QUALITY provides only shared infrastructure; per-check snapshot tests are a Definition of Done obligation, which keeps the dependency graph acyclic.
- Priority B adds the remaining checks. The disk map is split into traversal and reconciliation, categories, and tree with parity, and comes last because it is the most expensive check (236 of 365 s in the experiment). It does not depend on the Docker check, since Docker figures are never summed.
- Priority C closes documentation, verification, and release. The GitHub rename in WI-RELEASE needs separate owner authorization.
- Priority D holds measured optimization: parallel traversal is adopted only with benchmark evidence, and its outcome is the Rust revisit trigger recorded in WI-ADR-PYTHON.
- Priority E holds phase 2 by owner decision on 2026-11-02. WI-LEGACY-REMOVAL waits for WI-PREVIEW-CALLER so dupfind is removed only after its last known consumer migrates.
- No aggregate command is planned; verification and the experiment run each of the five commands.

---

Last Updated: 2026-11-02
Author: Orlando Bruno
