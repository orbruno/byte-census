---
artifact_schema: scrum-work-item
schema_version: 2.0.0
type: work-item
id: WI-DOCKER
work_item_kind: story
profile: compact
title: "Report Docker disk usage, images, and stopped containers"
parent: null
points: 3
status: in_progress
definition_of_done:
  path: ../Definition-of-Done.md
  version: "0.1.0"
dependencies: 
  - WI-CORE
  - WI-SUGGESTIONS
design_refs: []
verification_refs: []
superseded_by: null
relocated_to: null
disposition_reason: null
created: 2026-11-02
updated: 2026-11-02
author: Orlando Bruno
---

# WI-DOCKER - Report Docker disk usage, images, and stopped containers

## Outcome

A user sees what Docker occupies and what Docker itself reports as reclaimable.

## Acceptance Criteria

- AC-01: `byte-census docker scan` reports `docker system df` per type, the image inventory (repository, tag, size, created), dangling image count, and stopped containers.
- AC-02: A missing CLI or a stopped daemon exits 4 with a JSON error that says how to fix it.
- AC-03: Docker sizes are labeled as Docker-reported and are never added to host filesystem totals.
- AC-04: Findings carry catalog suggestions: `docker image prune` (low), `docker container prune` (medium), `docker system prune -a` and `docker volume prune` (high).

## Verification

Required checks:

- Fake-runner tests for available, missing, and daemon-down cases pass; JSON snapshot exists.

Evidence:

- Commit 1aefee2: four allowlisted docker argvs through the runner, exit 4 when the daemon or CLI is unavailable, Docker-reported sizes never summed; docker never executed in tests. Independent review pending.
- Closure: held open until the first CI run is green.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
