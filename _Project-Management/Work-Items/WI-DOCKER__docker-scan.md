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
status: proposed
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

- Not yet executed.

---
Last Updated: 2026-11-02
Author: Orlando Bruno
