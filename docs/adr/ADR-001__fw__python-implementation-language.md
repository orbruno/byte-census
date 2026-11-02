# Python as Implementation Language for byte-census

**Version**: 1.0
**Created**: 2026-11-02
**Author**: Orlando Bruno
**Status**: Accepted
**Area**: fw
**Related Documents**: [Traversal benchmark results](../benchmarks/2026-11-02-traversal/results.md), [WI-ADR-PYTHON](../../_Project-Management/Work-Items/WI-ADR-PYTHON__python-implementation-decision.md), CLI Creation playbook ADR-003 (Rust as Primary Implementation Language), CLI Creation playbook ADR-002 (LLM and Agent-Friendly Design Baseline)

---

## Executive Summary

byte-census, a deterministic, read-only macOS storage CLI, stays in Python (managed with `uv`, distributed with `uv tool`). The CLI Creation playbook defaults to Rust + Clap (its ADR-003); this record documents the departure and rejects a Rust rewrite. On 2026-11-02 the owner chose Python for four reasons: working Python code with its tests already exists; use is personal, so `uv tool` distribution is enough; startup latency does not matter for checks that run seconds to minutes; and the traversal benchmark indicates the limit is filesystem metadata throughput, not language. The choice carries one condition: documentation quality must match the playbook baseline (ADR-002 contracts, framework-generated help, SKILL.md). Rust is to be reconsidered if WI-PARALLEL-WALK cannot reach its target or if traversal time becomes the main complaint.

---

## 1. Problem Statement

### Context

The playbook's ADR-003 sets Rust + Clap v4 as the primary language for CLIs built from it, because Clap's derive API, `serde_json` and typed errors enforce the ADR-002 contracts (Output, Control, Discoverability, Safety) at compile time. byte-census began as a Python tool (`duplicate-finder-cli`) with working code and tests, and is being reshaped into a read-only storage CLI. Following the default means rewriting that code in Rust.

The open questions were:

- Is the Rust rewrite justified by performance, the main argument for a compiled language in a filesystem scanner?
- If not, what replaces the mechanical guarantees that Rust would provide for the ADR-002 contracts?

### Desired Outcome

A recorded, reviewable exception to the playbook default, with the evidence that supports it, its limits stated plainly, a condition that preserves the baseline, and a trigger for revisiting it.

---

## 2. Options Considered

### Option A: Rewrite in Rust + Clap v4 (playbook default)

**Pros**:
- Matches the playbook default and its scaffold and release tooling.
- Contracts such as stable JSON output and typed exit codes are enforced by the compiler.
- Single static binary, sub-millisecond startup.

**Cons**:
- Discards working Python code and its tests; the work must be redone and re-verified.
- Distribution advantages matter little for a tool used only by its owner.
- Startup latency gains are irrelevant when a check takes seconds to minutes.
- The benchmark does not show a traversal advantage large enough to pay for the rewrite (see Section 3).

### Option B: Keep Python, add parallel processes where needed ✅

**Pros**:
- Reuses the existing implementation and tests.
- `uv tool` installation is sufficient for personal use.
- The benchmark shows Python with multiple processes reaching the time of Rust with multiple threads on the measured tree.
- Work can be directed at the planned parallel walk (WI-PARALLEL-WALK) instead of a rewrite.

**Cons**:
- ADR-002 contracts are enforced by tests and discipline, not by the type system.
- Python threads give no traversal gain, so parallelism needs processes, with their coordination cost.
- Requires `uv` (and an interpreter it manages) on the machine.

### Option C: Keep Python without parallelism

Rejected as a plan: the benchmark shows a 1.6 times warm speedup from processes over a single process, so ignoring it leaves measured time unused.

---

## 3. Evidence

The committed benchmark is in [`docs/benchmarks/2026-11-02-traversal/`](../benchmarks/2026-11-02-traversal/results.md) (scripts `walk.py`, `walk_mp.py`, `walk.rs` beside the results). Machine: Apple Silicon, 8 performance and 2 efficiency cores. Tree: one development workspace folder.

### Equal-work run

`walk_mp.py` scans the root's own entries in the parent process and each child directory in a worker, so it visits the same entries as the single-process walk. All three methods agree exactly on **8,286,834,688 allocated bytes and 351,947 entries**.

- Python, 1 process: 13.3 s (pass 1, cache partly cold), 5.1 s (pass 2, warm).
- Python, 4 processes: 3.9 s, 3.6 s.
- Python, 10 processes: 3.7 s, **3.1 s warm**.

Ten processes take 3.1 s warm against 5.1 s for one process.

### Exploratory run (indicative only)

On the same tree, with warm cache and about 351,711 entries: Rust with 10 threads took **3.4 s**, Rust with 4 threads 5.5 s, Rust with 1 thread 11.9 s, `du -sk` 10.3 s, and `du` in 10 parallel processes 3.4 s. Python with 10 threads took 6.3 s against 6.2 s for one process, so **Python threads gain nothing**.

### Reading and limits

The data suggest the limit is filesystem metadata throughput, not language: parallel Python processes (3.1 to 3.7 s) land close to parallel Rust threads (3.4 s). The conclusion is that the two are **comparable**, not that they are proven equivalent. Caveats, stated plainly:

- The benchmark has no raw run logs; only the summarized results are committed.
- The Rust figures come from a separate exploratory run, not an equal-work controlled rerun against the Python runs.
- In that exploratory run the Python threads variant scanned a different scope (child-directory descendants only), so its entries are not identical to the single-process walk.
- Cold-cache behavior varies widely, and a larger tree was not measured. WI-PARALLEL-WALK owns that measurement.

---

## 4. Chosen Solution

**Decision**: Option B. byte-census stays in Python, managed with `uv` and installed with `uv tool`. The Rust rewrite is rejected for now. This is a deliberate exception to the playbook default, accepted on 2026-11-02 after the 2026-11-02 plan reviews.

Reasons:

1. Working Python code and its tests already exist; a rewrite would spend effort to reproduce existing behavior.
2. Use is personal, so `uv tool` distribution is enough and a static binary adds little.
3. Startup latency is irrelevant for checks that take seconds to minutes.
4. The benchmark indicates the bottleneck is filesystem metadata throughput, and Python processes reach a time comparable to Rust threads on the measured tree (with the caveats in Section 3).

### Condition: documentation quality matches the playbook baseline

The exception is valid only while byte-census meets the baseline that Rust would have enforced mechanically. Because Python does not enforce it at compile time, the following are required and verified by tests and review:

- The four ADR-002 contracts (Output O-01 to O-06, Control C-01 to C-05, Discoverability D-01 to D-05, Safety S-01 to S-05) are met, with tests covering JSON output stability, exit codes and ANSI-free piped output.
- `--help` is framework-generated from the option definitions (for example with Typer or Click), with no hand-maintained help text; examples follow the ADR-002 help format.
- A SKILL.md exists so an agent can drive the CLI, and it is kept in step with the command surface.

If these cannot be maintained, the argument that Python costs nothing in documentation quality fails, and this decision should be reopened.

---

## 5. Consequences

**Positive**:
- No rewrite cost; effort goes to the storage features and the parallel walk.
- Fast iteration with the existing test suite.

**Negative and accepted**:
- Contract enforcement relies on tests and review, not the compiler.
- Parallel traversal uses processes, adding coordination and, on a cold cache, results that vary.
- Installation depends on `uv`.
- The tool diverges from the playbook scaffold and release tooling, so those are not reused.

**Risks**:
- Benchmark evidence is thin (no raw logs, non-controlled Rust comparison). Mitigation: WI-PARALLEL-WALK re-measures with controlled, logged runs, including a larger tree and cold cache.
- Documentation drift from the baseline. Mitigation: the condition above, checked in review.

---

## 6. Revisit Trigger

Reconsider a Rust implementation if either holds:

- WI-PARALLEL-WALK cannot reach its target traversal time with Python processes; or
- traversal time becomes the main complaint in actual use.

---

## 7. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-11-02 | Keep Python; reject Rust rewrite; condition: documentation quality matches the playbook baseline | Existing tested code, personal use via `uv tool`, startup latency irrelevant, benchmark indicates metadata throughput is the limit and Python processes are comparable to Rust threads |

---

**Last Updated**: 2026-11-02 by Orlando Bruno
