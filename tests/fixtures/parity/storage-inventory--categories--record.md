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

### Scan root: <FIXTURE>/home/Library/Application Support - total 1.4 MB (0 permission/read errors)
- 900 KB  <FIXTURE>/home/Library/Application Support/Steam
- 500 KB  <FIXTURE>/home/Library/Application Support/MobileSync

### Managed categories
(well-known locations measured read-only; entries under a declared scan
root or nested in another category are shown but excluded from the sum)
- User caches: 300 KB
- Application support: 1.4 MB (informational; inside a declared scan root)
- App containers: 260 KB
- Group containers: 120 KB
- Developer data: 700 KB
- Device backups (inside Application support): 500 KB (informational; nested)
- Mail: 60 KB
- Messages: 92 KB
- Downloads: 452 KB
- Applications: <MACHINE_SIZE><MACHINE_ERRORS>

- Local snapshots: <SNAPSHOT_COUNT> present (managed system state; sizes not attributable without privileged inspection)
- Container storage: no docker CLI found

## Reconciliation (indicative)
- Filesystem used: <DF_USED>
- Measured scopes (scan roots + counted categories): <MACHINE_SIZE>
- Unexplained remainder: <MACHINE_SIZE> - system data, other
  users, purgeable space, local snapshots, and any scope overlaps.
  A large remainder means the audit has not yet accounted for the disk;
  it is a finding, not a conclusion.

## Incomplete Coverage
- /Applications: <MACHINE_ERRORS>

## Decision Queue
(empty by design - classify findings and record pending decisions per
`<SCHEMA_PATH>`; every action requires separate explicit authorization)
