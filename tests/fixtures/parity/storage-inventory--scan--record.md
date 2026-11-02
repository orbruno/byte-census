# Storage Inventory - <RUN_TS>

Read-only observation record. Classification, dispositions, and the
decision queue are human work; see the record contract:
`<SCHEMA_PATH>`

## Baseline
- <RUN_TS> `df -k /System/Volumes/Data` - used <DF_USED> of <DF_TOTAL>, <DF_AVAILABLE> available.
- <RUN_TS> `df -k /` (system volume) - used <SYSTEM_USED>.
- Volume Name:               <DISKUTIL_VALUE>
- File System Personality:   <DISKUTIL_VALUE>
- Container Total Space:     <DISKUTIL_VALUE>
- Container Free Space:      <DISKUTIL_VALUE>

## Findings (unclassified observations)

### Scan root: <FIXTURE>/scan - total 8.8 MB (0 permission/read errors)
- 4.5 MB  <FIXTURE>/scan/media
- 3.0 MB  <FIXTURE>/scan/archive
- 88 KB  <FIXTURE>/scan/projects
- 40 KB  <FIXTURE>/scan/docs
- 0 KB  <FIXTURE>/scan/empty

Large files (>1 MB, top 20; permission errors suppressed - coverage may be incomplete):
- 3.0 MB  <FIXTURE>/scan/media/movie.mov
- 2.0 MB  <FIXTURE>/scan/archive/old.zip
- 1.5 MB  <FIXTURE>/scan/media/clips/a.mp4
- 1.2 MB  <FIXTURE>/scan/root.bin

## Reconciliation (indicative)
- Filesystem used: <DF_USED>
- Measured scopes (scan roots + counted categories): 8.8 MB
- Unexplained remainder: <MACHINE_SIZE> - system data, other
  users, purgeable space, local snapshots, and any scope overlaps.
  A large remainder means the audit has not yet accounted for the disk;
  it is a finding, not a conclusion.

## Incomplete Coverage
- None recorded (large-file sweep still suppresses permission errors).

## Decision Queue
(empty by design - classify findings and record pending decisions per
`<SCHEMA_PATH>`; every action requires separate explicit authorization)
