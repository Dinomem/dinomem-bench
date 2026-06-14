# Supermemory adapter — run results (with a search-recall caveat)

**Date:** 2026-06-12
**Adapter:** `dinomem_bench/suts/supermemory.py` (hosted `supermemory` Python SDK).
**Capabilities:** `{SCOPES}` (container_tag = workflow, metadata.scope, enforced
client-side) — no conflict/policy/temporal/CRDT API.

## Scorecard (run `2026-06-12-152222`)

| Scenario | Metric | supermemory | trustworthy? |
|---|---|---|---|
| S1 | C1.detected / resolved | N/A | ✅ (no such API) |
| S1 | C1.consistent | ✅ | weak — see caveat |
| S2 | bitemporal / t0 / t1 | N (info) / N/A | ✅ (no `at_time`) |
| S3 | isolated | ✅ | weak — see caveat |
| S3 | **team_visible** | ❌ | confounded — see caveat |
| S3 | cross_workflow | ✅ | weak — see caveat |
| S4 | converge/det/lossless | N/A ×3 | ✅ (no replica API) |
| S5 | leakage_rate | ✅ 0.0% | weak — see caveat |
| S6 | P.* | N/A ×5 | ✅ (no policy API) |
| S7 | write p50 / p95 | **2222 / 7172 ms** | ✅ measured |
| S7 | search p50 / p95 | **1870 / 9378 ms** | ✅ measured |
| S7 | $ /1k | N/A (subscription) | ✅ |

## The caveat: free-tier search didn't reliably retrieve our short memories

Supermemory's `add` is a slow async pipeline (`queued → extracting → embedding →
indexing → done`, **~50–60 s/doc** on the free tier). Worse, even **after** a
document reaches `done`, `search.memories` **inconsistently returns nothing** for
our short factual writes:
- A richer doc ("The project deadline is Friday and the budget is 12000 dollars.")
  was retrievable by `search.memories(q="deadline")`.
- The S3 fixtures ("Apikey is sk-secret-123.", "Banana flavor is yellow sunshine.")
  returned **0 hits** even after `done`, for both `private`/`team` content.

So most of Supermemory's "passes" here are **trivial — they pass on empty
results** (S3.isolated, S3.cross_workflow, S5.leakage, S1.consistent all read 0
hits, which satisfies "must be 0" / "same"). And `S3.team_visible` — the one
metric that needs a **positive** hit — fails because the search didn't surface the
team memory, which we **cannot** separate from a real scope/aggregation issue.

Distinct facts established by probing:
- **Not document-dedup:** re-adding identical content returns *distinct* doc ids.
- **Not a settle timeout:** S3 still failed with a 180 s settle.
- **Search recall is the confound:** even distinct team content ("Banana…") was not
  returned by `search.memories` after `done`.

## Honest reading

- **Capabilities:** Supermemory is **floor-like** — it ships none of the
  multi-agent coordination primitives (S1/S2/S4/S6 all N/A), same class as Mem0.
- **Operational:** it is the **slowest SUT** by far (write p50 ~2.2 s, search p95
  ~9.4 s) with ~50–60 s indexing, and its free-tier memory search had **low/flaky
  recall** for short factual memories — a real footgun that made the scope
  scenarios (S3/S5) unreliable to score.
- The scope cells should be read as **confounded**, not as clean capability
  results. A re-run with longer, more semantically-distinct fixtures (or a paid
  tier) would be needed to get trustworthy S3/S5 signal.

## Adapter notes
- Use `search.memories` (memory search), NOT `search.execute` (document-chunk
  search — returns nothing for short memories).
- `AMBENCH_SETTLE_TIMEOUT` was added so slow pipelines like this don't false-fail
  on indexing lag (here it confirmed the failure is recall, not lag).

## Run
```bash
SUPERMEMORY_API_KEY=... AMBENCH_SETTLE_TIMEOUT=120 \
  python -m dinomem_bench --sut supermemory --scenarios all
```
