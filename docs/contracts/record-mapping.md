# Mapping to the Personal Digital Operation Record

Author: Orlando Bruno
Contract version: 1.0.0
Satisfies: WI-CONTRACTS AC-04

byte-census output can feed a `personal-digital-operation-record`, the portable evidence and authorization record of the Personal Digital Operations project. The record schema lives outside this repository.

## Target schema version

The record schema (`personal-digital-operation-record.schema.yaml`, JSON Schema draft 2020-12) carries no version field. Decision: the mapped version is identified by content:

| Key | Value |
|---|---|
| Schema document | `personal-digital-operation-record.schema.yaml` |
| Dialect | `https://json-schema.org/draft/2020-12/schema` |
| SHA-256 of the file | `33ce86462a5eb9ee722e459f4fc3774c09b4c28f07ec6d8f6d873c84ce478b07` |
| Observed | 2026-11-02 |

If the hash changes, this mapping must be reviewed before it is used again.

## Finding mapping

One CLI finding with a byte measure becomes one record finding. The record forbids extra keys (`additionalProperties: false`), so CLI-only fields are folded into `evidence`.

| Record field | Required | Source in CLI output | Rule |
|---|---|---|---|
| `id` | yes | `finding.id` | Copied unchanged. |
| `target` | yes | `finding.target` | Copied unchanged. |
| `size_kb` | yes | `finding.allocated_bytes` | `ceil(allocated_bytes / 1024)`, matching `du -k` rounding. For Docker findings: `ceil(details.docker_reported_size_bytes / 1024)`. |
| `measured_with` | yes | `meta.tool`, `meta.command` | `byte-census <version> <command> (allocated_bytes)`; for Docker findings `(docker_reported_size_bytes)`. |
| `owner` | no | `classification.owner` | Copied; empty string when unknown. Always present in the mapped record. |
| `status` | yes | `classification.status` | `unknown`. |
| `recovery` | yes | `classification.recovery` | `unknown`. |
| `sensitive` | no | none | Omitted: byte-census does not inspect content meaning. |
| `evidence` | no | `kind`, `caveats`, `see_check`, `meta.captured_at` | `"Observed by byte-census at <captured_at>; kind <kind>; caveats <codes or none>; see <see_check or none>. Not classified."` |
| `confidence` | yes | `classification.confidence` | `low`. |
| `disposition` | yes | `classification.disposition` | `investigate`. |

Findings without any byte measure are not mapped. Mapped Docker findings keep their Docker-reported size and are never summed into any record total (see [quantities.md](quantities.md#docker-figures)).

## Operation-level mapping

| Record field | Source |
|---|---|
| `operation.observation_only` | `true` (byte-census never mutates). |
| `operation.date` | Date part of `meta.captured_at`. |
| `operation.scope.roots` | `meta.scope.roots[].path` (at least one; `docker scan` alone cannot populate a record). |
| `operation.scope.exclusions` | `meta.scope.skipped_mounts`. |
| `operation.scope.incomplete` | `meta.incomplete_coverage[].path`, plus `source:<name>` for each `unavailable_sources[]` entry with reason `failed` or `timed_out` (see below). |
| `operation.purpose`, `platform`, `operator`, `device` | Not produced by byte-census; supplied by the operator. |
| `baseline[]` | From disk map `data.system`, one item per source that returned a value, in this order: `df -k /System/Volumes/Data`, `df -k /`, `diskutil info /`, `tmutil listlocalsnapshots /`. `measured_at` = `meta.captured_at`, `command` = the argv joined by spaces, `observation` = a one-line summary in bytes. |
| `decision_queue` | `[]`. |

Unavailable baseline sources. Decision: the data-volume `df` is always present when disk map succeeded, because disk map exits 4 without it. An optional source (`df -k /`, `diskutil`, `tmutil`) that is unavailable is omitted from `baseline`, never represented by a placeholder item. If its `unavailable_sources` reason is `failed` or `timed_out`, it appears in `operation.scope.incomplete` as `source:<name>`; if the reason is `not_installed`, it is omitted entirely. A record built without a disk map result has `baseline: []`, which the schema allows.

Combining commands. Decision: a record may combine several command results. `scope.roots`, `exclusions`, and `incomplete` are sorted unions without duplicates; findings follow command order (`docker scan`, `caches scan`, `artifacts scan`, `duplicates scan`, `disk map`) and then each result's own finding order. Finding IDs do not collide across commands because each command has its own prefix.

Decision: suggestions are not converted into `decision_queue` items automatically. The record requires an expected benefit, a recovery path, and a verification plan per item, which are human judgments; this keeps the queue empty by design, as storage-inventory.sh did. When an operator adds an item by hand, the suggestion supplies: `proposed_action` = "Proposal: " + `command`; `finding_id` = one of `finding_ids`; `reversibility` = `reversible` when `reversible` is true, else `irreversible`; `authorization.required` = `true`, `approved_by` = `""`.

## Validation evidence

Validation against the record schema is a local check, because the schema is not part of this repository. CI does not run it.

Representative record: [examples/mapped-record.example.json](examples/mapped-record.example.json), built by applying this mapping to all five command examples (32 findings, 4 baseline items; `purpose`, `platform`, and `operator` are placeholders an operator would supply).

Command (the schema file is read-only input; `SCHEMA.yaml` is its local path):

```sh
shasum -a 256 SCHEMA.yaml
uv run --no-project --with jsonschema --with pyyaml python -I -c \
  "import json,sys,yaml,jsonschema; jsonschema.Draft202012Validator(yaml.safe_load(open(sys.argv[2]))).validate(json.load(open(sys.argv[1]))); print('valid')" \
  docs/contracts/examples/mapped-record.example.json SCHEMA.yaml
```

Evidence, 2026-11-02:

| Item | Result |
|---|---|
| Schema SHA-256 | `33ce86462a5eb9ee722e459f4fc3774c09b4c28f07ec6d8f6d873c84ce478b07`, matches the pin above |
| Validator | jsonschema 4.26.0, Draft 2020-12, with PyYAML 6.0.3 |
| Result | Pass: printed `valid`, exit 0, no errors and no fixes needed |
| Negative control | Same record with one `status` set to `stale` and one `size_kb` removed: the validator reported `'size_kb' is a required property` and `'stale' is not one of [...]`, so the check rejects invalid records |

Rerun this check whenever this mapping, the examples, or the schema hash changes, and record the new result here.

---

Last Updated: 2026-11-02
Author: Orlando Bruno
