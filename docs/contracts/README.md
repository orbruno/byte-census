# byte-census Observation Contracts

Author: Orlando Bruno
Contract version: 1.0.0
Work Item: WI-CONTRACTS (`_Project-Management/Work-Items/WI-CONTRACTS__observation-contracts-and-parity.md`)

byte-census is a deterministic, read-only macOS storage CLI with five commands: `docker scan`, `caches scan`, `artifacts scan`, `duplicates scan`, and `disk map`. The legacy `dupfind` command stays as a frozen v1 adapter. These documents are the contracts that implementation and tests follow.

## Documents

| Document | Contents | Acceptance criteria |
|---|---|---|
| [quantities.md](quantities.md) | Byte glossary, hard links, volume boundary, Docker figures, APFS clone limitation, incomplete coverage and privacy denials, cost fields and null semantics | AC-01, AC-02, AC-05, AC-07 |
| [envelope.md](envelope.md) | `{data, meta}` envelope, finding and suggestion shapes, IDs, `see_check`, ordering, status, error object, exit codes, schema version policy | AC-03 |
| [examples/](examples/) | One JSON example per command and the error object, at `schema_version` 1.0.0, plus the mapped record | AC-03, AC-04 |
| [argv-allowlist.md](argv-allowlist.md) | Exact argv table for every external command | AC-06 |
| [record-mapping.md](record-mapping.md) | Mapping to the personal digital operation record | AC-04 |
| [parity-matrix.md](parity-matrix.md) | Retain, change, or defer for the replaced collector and the experiment preview | AC-09 |
| [adr-002-compliance.md](adr-002-compliance.md) | ADR-002 requirements: met, adapted, or not applicable | AC-10 |
| [legacy-exit-codes.md](legacy-exit-codes.md) | dupfind exit-code matrix tied to legacy tests | AC-08 |

## Examples

| File | Command | Shows |
|---|---|---|
| [docker-scan.json](examples/docker-scan.json) | `byte-census docker scan` | Docker-reported figures with null host bytes, image inventory, stopped containers, four risk-ordered suggestions, `status: complete` |
| [caches-scan.json](examples/caches-scan.json) | `byte-census caches scan` | Cache folders and a tool cache outside `~/Library/Caches`, a privacy denial, npm `not_installed` |
| [artifacts-scan.json](examples/artifacts-scan.json) | `byte-census artifacts scan ~/Projects` | Two artifacts with regeneration commands and per-finding suggestions, a permission denial |
| [duplicates-scan.json](examples/duplicates-scan.json) | `byte-census duplicates scan ~/Downloads` | One group with a merged hard link, `content_bytes_read`, a dataless file and a changed file |
| [disk-map.json](examples/disk-map.json) | `byte-census disk map --scan-root "$HOME/Library/Application Support" --scan-root ~/Library/Developer/Xcode` | Two roots; a category equal to a root, one inside a root, one enclosing a root (contributes only its remainder, with a merged hard link), and a tool cache inside a category; `reconciliation.contributions` summing to `measured_allocated_bytes`; signed delta, system context, tree, a skipped mount, empty suggestions |
| [error.json](examples/error.json) | `byte-census docker scan` with the daemon down | Error object, exit 4 |
| [mapped-record.example.json](examples/mapped-record.example.json) | none (derived) | The five examples mapped to a personal digital operation record and validated against the record schema ([record-mapping.md](record-mapping.md#validation-evidence)) |

Example paths use the placeholder home `/Users/example`. Values are illustrative; IDs follow the ID rule in envelope.md.

## Decisions recorded in these contracts

Each open point the sources left is marked `Decision:` in the document that owns it, for review.

---

Last Updated: 2026-11-02
Author: Orlando Bruno
