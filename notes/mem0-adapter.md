# Mem0 adapter — run results

**Date:** 2026-06-12
**Adapter:** `dinomem_bench/suts/mem0.py` (hosted `mem0ai` Python `MemoryClient`).
**Capabilities:** `{SCOPES}` only — emulated via metadata filtering (Mem0 stores
no scope label). No conflict/policy/temporal/CRDT API → those score N/A.

## Scorecard

| Scenario | Metric | mem0 |
|---|---|---|
| S1 | C1.detected / resolved | N/A (no conflict/policy API) |
| S1 | C1.consistent | ✅ Y |
| S2 | T1.bitemporal | ℹ️ N (no `at_time`) · t0/t1 N/A |
| S3 | S3.isolated | ✅ Y |
| S3 | S3.team_visible | ❌ **N** (see finding) |
| S3 | S3.cross_workflow | ✅ Y |
| S4 | converge/deterministic/lossless | N/A ×3 (no replica API) |
| S5 | S5.leakage_rate | ✅ 0.0% |
| S6 | P.*.correct / surfaced | N/A ×5 (no policy API) |
| S7 | Op.write_p50 / p95 | ℹ️ 1143 / 1451 ms |
| S7 | Op.search_p50 / p95 | ℹ️ 507 / 597 ms |
| S7 | Op.$ /1k | N/A (server-side subscription, not client-observable) |

(S7 run at reduced size — `AMBENCH_S7_WRITES=40 SEARCHES=20` — so it doesn't burn
the free tier's 1k-retrieval/month quota; latency percentiles are size-robust.)

## The finding: Mem0 scores at the floor — and below it on one metric

Mem0 is a category-leading *memory* product, but on the **multi-agent**
benchmark it advertises **none** of the coordination primitives: no conflict
detection, no resolution policies, no temporal queries, no CRDT. So S1 (detect/
resolve), S2, S4, S6 are all **N/A** — identical to the raw pgvector floor. The
benchmark's thesis, confirmed: *a managed memory system without coordination
primitives is indistinguishable from a vector store on these scenarios.*

**Worse than the floor on S3.team_visible.** Verified directly (`get_all`): Mem0
**dedups identical content** — re-`add`ing the same fact returns the *same* id and
**ignores the metadata/scope change**, so a fact written `private` then re-written
`team` stays private. You cannot widen a fact's visibility by re-writing it.
(Mem0's team scope *does* work for *distinct* content; it's specifically the
dedup-on-scope-upgrade that fails.) pgvector — which stores every row verbatim —
passes this; Mem0 fails it.

## Cross-system comparison so far

| Metric | pgvector (floor) | **mem0** | dinomem |
|---|---|---|---|
| S1 conflict detect + resolve | N/A | N/A | **✅ ✅** (only one) |
| S1 read consistency | ✅ | ✅ | ✅ |
| S2 temporal (t0/t1) | N/A | N/A | param Y, but t0/t1 ❌ (gap) |
| S3 isolated / cross-wf | ✅ / ✅ | ✅ / ✅ | ✅ / ✅ |
| S3 team_visible | ✅ | **❌ (dedup)** | ✅ |
| S4 CRDT | N/A | N/A | N/A (no replica API) |
| S5 workflow isolation | ✅ 0% | ✅ 0% | (deferred) |
| S6 policies | N/A | N/A | supported (deferred, Gemini quota) |
| S7 write p50 | 307 ms | 1143 ms | (deferred) |
| S7 search p50 | 309 ms | 507 ms | (deferred) |
| S7 cost | ~$0 marginal | subscription (n/a per-op) | subscription (n/a per-op) |

**Reading it:** On multi-agent coordination, **only DinoMem fills S1** (the one
metric that needs a real memory system); Mem0 ties the floor and *loses* one
metric to it; S3/S5 don't separate anyone. DinoMem's temporal is incomplete (S2
gap); its CRDT, by contrast, is now testable black-box — CRDT V3 ships a replica/
sync API (S4 is drivable end-to-end against DinoMem, the only SUT that can; this
note's run predates it). Latency: pgvector fastest
(embedding-bound ~307 ms), Mem0 ~3–4× slower on writes (~1.1 s, hosted + its own
processing). DinoMem's S2/S6/S7 await a Gemini-quota reset.

## Harness improvements from this adapter (committed)
- `Scenario.settle()` now also guards S3 (wait for index-visibility, so async SUTs
  aren't scored on un-indexed state).
- `AMBENCH_S7_WRITES` / `AMBENCH_S7_SEARCHES` env to scale S7 for rate/quota-limited
  hosted SUTs (default stays the DESIGN's 1000/500).
- `SUTAdapter.cost_observable` → S7 reports server-side cost as `N/A`, not a
  misleading `$0`, for hosted SUTs.

## Run
```bash
MEM0_API_KEY=... .venv/bin/python -m dinomem_bench --sut mem0 --scenarios all
# S7 at full size burns 500 of the 1k/mo free retrievals — use AMBENCH_S7_* to scale down
```
