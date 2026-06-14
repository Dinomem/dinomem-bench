# pgvector adapter — first real SUT run

**Date:** 2026-06-12
**Adapter:** `dinomem_bench/suts/pgvector.py`
**Setup:** Postgres `pgvector/pgvector:pg16` (docker), embeddings
`text-embedding-3-small` (1536-dim, pinned), `lists=100` ivfflat cosine index.
**Run:** `python -m dinomem_bench --sut pgvector --scenarios all` (`runs/2026-06-12-012323`).

The first non-fake SUT — and the floor the DESIGN is built around. It validates
that the harness scores a raw vector store the way the methodology intends.

## Scorecard

| Scenario | Metric | pgvector | why |
|---|---|---|---|
| S1 | C1.detected | N/A | no conflict detection (no extraction) |
| S1 | C1.resolved | N/A | no resolution policies |
| S1 | C1.consistent | ✅ Y | deterministic read — pure retrieval |
| S2 | T1.bitemporal | ℹ️ N | no `at_time` support |
| S2 | T1.t0 / t1 | N/A | — |
| S3 | S3.isolated / team_visible / cross_workflow | ✅ Y ×3 | scope is a `WHERE` clause |
| S4 | S4.converge / deterministic / lossless | N/A ×3 | no vector-clock/replica API |
| S5 | S5.leakage_rate | ✅ 0.0% | workflow isolation is a `WHERE` clause |
| S6 | P.*.correct / surfaced | N/A ×5 | no conflict policies |
| S7 | Op.write_p50/p95_ms | ℹ️ 307 / 452 | embedding-API-bound |
| S7 | Op.search_p50/p95_ms | ℹ️ 309 / 511 | embedding-API-bound |
| S7 | Op.write_$ / search_$ per 1k | ℹ️ $0.0001 / $0.0001 | text-embedding-3-small |

**Totals: 5 pass · 0 fail · 12 N/A · 0 crash · 7 info.**

## Reading the result

This is the baseline doing its job (DESIGN §3): pgvector **passes exactly the
metrics that don't need a memory system** — read consistency (S1.consistent),
scope enforcement (S3), workflow isolation (S5) — all of which are plain SQL
`WHERE` filters over a vector index. It is **N/A on the 12 metrics that do need
one**: conflict detection + resolution (S1), temporal validity (S2), CRDT
convergence (S4), and policy fidelity (S6).

So S3 and S5 **do not separate** a memory system from a raw vector store; the
managed systems have to earn their keep on S1/S2/S4/S6. That contrast is the
whole point of the benchmark and is what the DinoMem / Mem0 adapters will show.

### Latency is embedding-bound, not DB-bound
~300 ms/op is the OpenAI embedding round-trip; the ivfflat cosine query itself is
sub-millisecond. A self-host pgvector with a local embedding model would be far
faster — the number here reflects "pgvector + hosted OpenAI embeddings" out of
the box, which is the honest comparison against hosted systems that also embed
server-side. (Cost is negligible: ~$0.0002 for the full S7 workload of 1,000
writes + 500 searches.)

## Adapter notes
- `capabilities = {SCOPES}` only. `check_conflicts` / `set_policy` / `replica_*`
  inherit `Unsupported` from the base → scored N/A, never crash.
- Reproduce: `docker run -d --name amb-pg -e POSTGRES_PASSWORD=bench -e
  POSTGRES_DB=bench -p 5433:5432 pgvector/pgvector:pg16`, then set
  `DATABASE_URL` + `OPENAI_API_KEY` and run. Deps: `psycopg[binary]`, `openai`
  (the `pgvector` optional extra).
- Harness fixes this run surfaced: S5 leak = wf-B *content* in results (not "any
  hit", since a vector store always returns top-k nearest); S2.bitemporal is INFO
  (a capability fact), not a fail.
