# Zep adapter — run results: the only SUT that fills S2

**Date:** 2026-06-12
**Adapter:** `dinomem_bench/suts/zep.py` (hosted `zep-cloud` Python SDK, Graphiti
temporal knowledge graph).
**Capabilities:** `{TEMPORAL}`. Graph-centric (a `graph_id` is the isolation unit;
no per-agent scope), so SCOPES / conflict-surfacing / policy / CRDT are N/A.

## Scorecard

| Scenario | Metric | zep |
|---|---|---|
| S1 | C1.detected / resolved | N/A (no conflict-surfacing/policy API) |
| S1 | C1.consistent | ✅ Y |
| S2 | T1.bitemporal | ℹ️ **Y** |
| S2 | **T1.t0** | ✅ **Y** — `at_time=T0` → only "green" |
| S2 | **T1.t1** | ✅ **Y** — `at_time=T1` → only "red" |
| S3 | isolated / team_visible / cross_workflow | N/A ×3 (no per-agent scope) |
| S4 | converge / deterministic / lossless | N/A ×3 (no replica API) |
| S5 | leakage_rate | N/A (no scope capability) |
| S6 | P.* | N/A ×5 (no policy API) |
| S7 | write p50 / p95 | ℹ️ **305 / 416 ms** |
| S7 | search p50 / p95 | ℹ️ **302 / 406 ms** |
| S7 | $ /1k | N/A (subscription) |

## The headline: Zep is the only SUT that fills S2

Zep extracts facts as graph edges with full bitemporal validity and **automatically
invalidates** a fact when a later one contradicts it. Verified directly:

```
add "Project status is green."  created_at=2026-01-01T00:00:00Z
add "Project status is red."    created_at=2026-01-01T00:01:00Z
# ~50s of async graph processing later:
edge "Project status is green."  valid_at=00:00:00Z  invalid_at=00:01:00Z   <- auto-invalidated
edge "Project status is red."    valid_at=00:01:00Z  invalid_at=None        <- current
```

The adapter sets `created_at` on `graph.add` (so we control the episode times) and
answers `at_time` by filtering edges on `valid_at <= t < invalid_at`. Result:
`at_time=T0` → green only; `at_time=T1` → red only. **Zep is the first and only
SUT to pass S2** — pgvector / mem0 / supermemory are N/A (no temporal), and
DinoMem accepts `atTime` but returns both facts (its S2 gap).

This makes **S2 a genuinely differentiating scenario**, the temporal analogue of
S1: just as only DinoMem fills conflict detection+resolution, only Zep fills
temporal validity. Different systems, different strengths — exactly the design's
thesis (DESIGN §3: "best memory system is a category error").

## Operational notes
- **Fast**: write p50 ~305 ms, search p50 ~302 ms — on par with the pgvector floor,
  far faster than mem0 (~1.1 s) and supermemory (~2.2 s). (`graph.add` returns
  quickly; fact extraction is async in the background.)
- **Async extraction ~tens of seconds**: S2 (and any contradiction-dependent flow)
  must wait for processing — handled by `Scenario.settle()` waiting until the new
  fact is current (`AMBENCH_SETTLE_TIMEOUT` was set to 90 s for this run).
- **No agent scope**: Zep isolates by `graph_id` (mapped from workflow_id), but has
  no private/team/global-per-agent concept, so S3/S5 are N/A. Workflow-level
  isolation does work (different graph_id), it just isn't the scope model S3/S5 test.
- Contradiction handling exists (auto-invalidation) but there's **no conflict-
  surfacing API** (no `check_conflicts`), so S1.detected / S6 are N/A — Zep's
  resolution shows up through S2 instead.

## Run
```bash
ZEP_API_KEY=... AMBENCH_SETTLE_TIMEOUT=90 \
  python -m dinomem_bench --sut zep --scenarios all
```
