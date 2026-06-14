# Cognee adapter — run results (graph-RAG; slowest; no isolation in zero-setup mode)

**Date:** 2026-06-13
**Adapter:** `dinomem_bench/suts/cognee_sut.py` — self-host Cognee 1.1.2
(SQLite+LanceDB+Kuzu), async `add → cognify → search`, `SearchType.CHUNKS` for
verbatim retrieval, `ENABLE_BACKEND_ACCESS_CONTROL=false` (zero-setup, no
user/tenant auth). **Capabilities: `{}` (none)** — see the isolation finding.

## Scorecard

| Scenario | Metric | cognee |
|---|---|---|
| S1 | C1.detected / resolved | N/A (no conflict/policy API) |
| S1 | C1.consistent | ✅ Y |
| S2 | bitemporal / t0 / t1 | N (info) / N/A (no `at_time`) |
| S3 | isolated / team_visible / cross_workflow | N/A ×3 (no enforced scope — see below) |
| S4 | converge / det / lossless | N/A ×3 |
| S5 | leakage_rate | N/A (no enforced scope — see below) |
| S6 | P.* | N/A ×5 |
| S7 | write p50 / p95 | ℹ️ **20965 / 28168 ms** |
| S7 | search p50 / p95 | ℹ️ 1919 / 1927 ms |
| S7 | $ /1k | N/A (LLM + embedding, server-side cost) |

## Finding 1: no isolation in the zero-setup mode (the important one)

I first mapped scope → Cognee **datasets** (team = one dataset/workflow, private =
a per-agent dataset; a reader searches team + its own private). S3 *appeared* to
pass — but **S5 then leaked 100%** (every workflow-A search surfaced workflow-B
content; run `2026-06-13-053651`). Diagnosis:

> With `ENABLE_BACKEND_ACCESS_CONTROL=false`, `cognee.search(datasets=[...])`
> **ignores the dataset filter and queries the GLOBAL knowledge graph.** The S3
> "passes" were adapter artifacts — the reader's datasets didn't exist yet, so the
> adapter short-circuited to `[]`, not real isolation. When both workflows' data
> coexist (S5), there is no isolation at all.

Cognee's dataset/workflow isolation lives in its **access-control / multi-tenant
layer**, which requires per-user/tenant auth setup we deliberately skipped for a
zero-infra run. So scope/isolation is **untested → N/A** (capabilities dropped to
`{}`); the 100% leak is recorded here as the evidence. A future run with access
control enabled + a real user context could test S3/S5 properly.

## Finding 2: by far the slowest SUT

`write p50 ≈ 21 s` (add + cognify run LLM entity/graph extraction on every write),
`p95 ≈ 28 s` — ~10× mem0, ~70× pgvector/zep/langmem. S5/S7 had to be scaled down
(`AMBENCH_S5_WRITES=3`, `AMBENCH_S7_WRITES=5`) just to finish. `cognify` also
*rewrites* text under `GRAPH_COMPLETION` (returned "The deadline is Friday." from a
longer input), so the adapter uses `CHUNKS` (raw, verbatim) for retrieval.

## Honest reading

Cognee is a **graph-RAG** system. On this multi-agent benchmark it exposes **no
coordination primitive** (S1 detect/resolve, S2 temporal, S4 CRDT, S6 policies all
N/A) and **no enforced scope without its access-control layer** (S5 leaked 100% in
the zero-setup mode). What it does provide — entity/graph extraction + RAG answers
— isn't what S1–S7 test. Operationally it is the slowest by a wide margin.

## Adapter notes
- async `add`/`cognify`/`search` driven from a single persistent event loop reused
  across scenarios (cognee's DB engines bind to a loop); `prune` per scenario.
- `ENABLE_BACKEND_ACCESS_CONTROL=false` + `LLM_API_KEY=OPENAI_API_KEY`; SQLite+
  LanceDB+Kuzu auto-create locally.
- `AMBENCH_S5_WRITES` env added so very-slow SUTs can run S5 at small N.

## Run
```bash
OPENAI_API_KEY=... AMBENCH_S5_WRITES=3 AMBENCH_S7_WRITES=5 AMBENCH_S7_SEARCHES=3 \
  python -m dinomem_bench --sut cognee --scenarios all   # extra: cognee
```
