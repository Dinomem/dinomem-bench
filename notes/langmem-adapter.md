# LangMem adapter — run results: the cleanest floor

**Date:** 2026-06-13
**Adapter:** `dinomem_bench/suts/langmem.py` — LangGraph `InMemoryStore` + an
OpenAI embedding index (`text-embedding-3-small`), namespaces for scoping. This is
the DESIGN's "LangMem floor, LangGraph backend, OpenAI embeddings" minus the
Postgres infra (same semantics, zero infra).
**Capabilities:** `{SCOPES}`. No conflict/policy/temporal/CRDT API.

## Scorecard

| Scenario | Metric | langmem |
|---|---|---|
| S1 | C1.detected / resolved | N/A |
| S1 | C1.consistent | ✅ Y |
| S2 | bitemporal / t0 / t1 | N (info) / N/A | 
| S3 | S3.isolated | ✅ Y |
| S3 | **S3.team_visible** | ✅ **Y** |
| S3 | S3.cross_workflow | ✅ Y |
| S4 | converge / det / lossless | N/A ×3 |
| S5 | leakage_rate | ✅ 0.0% |
| S6 | P.* | N/A ×5 |
| S7 | write p50 / p95 | ℹ️ 303 / 404 ms |
| S7 | search p50 / p95 | ℹ️ 304 / 412 ms |
| S7 | $ /1k | N/A (OpenAI embedding cost, not instrumented) |

**Totals: 5 pass · 0 fail · 12 N/A · 7 info.** Identical capability profile to the
pgvector floor.

## Reading it

LangMem is a **clean floor** — like pgvector, it passes the retrieval + filtering
metrics (read consistency, all of S3, S5 isolation) and is N/A on every multi-agent
coordination metric (S1/S2/S4/S6). It ships no conflict detection, policies,
temporal queries, or CRDT.

The interesting contrast with the *other* floors:
- **Verbatim stores pass `S3.team_visible`** — pgvector ✅ and langmem ✅ store each
  write as a distinct row, so re-writing a fact at `team` scope creates a
  team-visible memory.
- **Dedup/aggregating stores fail it** — mem0 ❌ (content-dedup ignores scope) and
  supermemory ❌ (memory aggregation / flaky recall). So the same "floor" capability
  bucket splits on whether the system mangles identical content.

Operationally LangMem is **synchronous + in-process** (the only latency is the
OpenAI embedding call, ~300 ms), so unlike the hosted SUTs there's no async
indexing — `Scenario.settle()` returns immediately. write/search p50 ~303 ms,
on par with pgvector and zep, far faster than mem0 (~1.1 s) / supermemory (~2.2 s).

## Adapter notes
- Backed by `InMemoryStore(index={"dims":1536,"embed":OpenAIEmbeddings,"fields":["content"]})`
  — the index is what makes `store.search` a vector search.
- workflow_id → namespace `(ns, workflow_id)`; scope/writer in the value, enforced
  client-side (same emulation as the other floors).
- Cost: the per-op OpenAI embedding cost is the same order as pgvector (~$0.0001/1k)
  but isn't instrumented through LangChain here → reported N/A.

## Run
```bash
OPENAI_API_KEY=... python -m dinomem_bench --sut langmem --scenarios all  # extra: langmem, langchain-openai, langgraph
```
