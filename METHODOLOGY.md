# Scoring methodology

> **Conflict of interest / integrity.** DinoMem's maintainers build *and* run this
> benchmark, and DinoMem is one of the systems under test. This document is the
> mitigation: it publishes, in full, exactly how every metric is decided — so that
> "DinoMem wins S1" means a specific deterministic assertion passed, not that the
> authors said so. See also [`README.md`](./README.md) and `DESIGN.md §9`.

This is the companion to [`DESIGN.md`](./DESIGN.md). DESIGN says *what* each
scenario is and *why*; this file says **how a pass / fail / na / info is decided**
for every metric, and **how to reproduce a run** so you get the same numbers.

The benchmark's central reproducibility claim is simple:

> **The deterministic assertions in the scenario code ARE the judge. There is no
> LLM-as-judge in any shipped scenario.** Every verdict is a Python comparison over
> the SUT's API responses (`==`, `in`, `len(...) == 0`, set equality). Anyone can
> read the exact assertion in `dinomem_bench/scenarios/sN_*.py`, re-run, and get
> the same result without an API key for any judging model.

If a future scenario ever uses an LLM to judge semantic correctness, its **full
prompt + the model's completion** are recorded per call in
`runs/<run_id>/judgements.jsonl`, and the prompt is published here. **As of this
version that file is written empty** — no scenario judges with an LLM.

---

## 1. The five metric statuses

Every cell in the matrix is one of these (defined in
`dinomem_bench/scenarios/base.py`):

| Status | Marker | Meaning | Counts as a failure? |
|---|---|---|---|
| `pass`  | ✅ | The deterministic assertion held. | — |
| `fail`  | ❌ | The SUT answered, but the answer violates the assertion (wrong answer). | **Yes** |
| `na`    | — | The SUT's API cannot perform what the metric needs (it raised `Unsupported` or lacks the `Capability`). | **No** — explicitly not a failure. |
| `crash` | 💥 | The SUT raised an unexpected exception / 5xx / timed out, even after one re-run. | **Yes** (a defect, distinct from a wrong answer). |
| `info`  | ℹ️ | An operational measurement (latency, $/1k) with no correct/incorrect — S7, plus the descriptive `T1.bitemporal` capability flag. | — |

`na` vs `fail` is the most important distinction and the anti-gerrymandering
guard: a system without temporal queries is **not penalised** on a temporal
metric — it records `na`. We do this so the matrix never punishes a system for
not having a feature it never claimed; it only penalises *wrong answers* (`fail`)
and *defects* (`crash`).

### How `na` happens mechanically

Each scenario declares `requires: frozenset[str]` of `Capability` flags, and each
adapter declares the `capabilities` it advertises. A scenario method that needs a
capability the SUT lacks either (a) sees `sut.supports(cap) == False` and emits
`na` directly, or (b) calls the method and the adapter raises
`dinomem_bench.adapter.Unsupported`, which the scenario catches and records as
`na`. Both paths are visible in the scenario source.

---

## 2. Per-scenario assertions (S1–S7)

Every metric below names the exact predicate the scenario evaluates. "Settle"
means the scenario polls `search()` until the just-written fact is visible
(bounded, best-effort) so async-indexing SUTs are given time to index before the
assertion runs; it is a no-op for in-process SUTs. Settling never sleeps a fixed
wall-clock interval as part of correctness — it waits on a *condition*.

### S1 — Contradictory writes (`s1_contradictory.py`)

Requires `CONFLICTS` + `POLICIES`. Setup: set policy `planner_wins` on the
workflow, then `planner` writes "Deadline is Friday." (settle), then `executor`
writes "Deadline is Monday."

| Metric | Status if… | Decided by |
|---|---|---|
| `C1.detected` | `pass` if `len(check_conflicts("Deadline is Monday.", …)) > 0`; `na` if no `CONFLICTS` capability. | A non-empty conflict list before the 2nd write. |
| `C1.resolved` | `pass` if a read for "Deadline" returns a hit containing "friday" and **none** containing "monday"; `na` if no `POLICIES` capability. | Under `planner_wins`, only the planner's fact survives the read. |
| `C1.consistent` | `pass` if two readers (`reader-a`, `reader-b`) get the **same sorted set of contents**. | `sorted(a) == sorted(b)`. Pure-retrieval systems pass this. |

### S2 — Temporal validity (`s2_temporal.py`)

Requires `TEMPORAL`. Agent writes "Project status is green." then "…is red."; the
SUT assigns each write a `created_at`, which the scenario uses as the `at_time`
query point (no wall-clock sleep).

| Metric | Status if… | Decided by |
|---|---|---|
| `T1.bitemporal` | **`info`** (Y/N), never pass/fail — it is a *descriptive capability fact*, "many do not". | `sut.supports(TEMPORAL)`. |
| `T1.t0` | `pass` if `search(at_time=T0)` returns "green" and **not** "red"; `na` if no temporal support / `at_time` raises `Unsupported`. | Point-in-time read at the first write's timestamp. |
| `T1.t1` | `pass` if `search(at_time=T1)` returns "red" and **not** "green"; `na` as above. | Point-in-time read at the second write's timestamp. |

> DinoMem **fails** `T1.t0`/`T1.t1`: it accepts `at_time` (so it is not `na`) but
> returns both facts. Zep passes (it invalidates the stale fact via `invalid_at`).
> This is enumerated in the matrix's "Where DinoMem loses" section.

### S3 — Scope enforcement (`s3_scope.py`)

Requires `SCOPES`. Agent A writes a `private` memory; agent B (same workflow,
different agent) searches.

| Metric | Status if… | Decided by |
|---|---|---|
| `S3.isolated` | `pass` if B's search for A's private memory returns **0 hits**; `na` if no `SCOPES`. | `len(b_hits) == 0` after A's write is confirmed indexed. |
| `S3.team_visible` | `pass` if, after A re-writes the same fact at `team` scope, B sees `> 0` hits. | `len(b_hits2) > 0`. (mem0/supermemory **fail** here: dedup ignores the scope change.) |
| `S3.cross_workflow` | `pass` if a reader in a *different* workflow sees **0** of workflow-A's facts. | `len(x_hits) == 0`. |

### S4 — Concurrent writes / CRDT (`s4_crdt.py`)

Requires `VECTOR_CLOCK`. **Drivable end-to-end against DinoMem** as of CRDT V3,
which ships a real op-based LWW-Register CvRDT engine + a black-box replica/sync
API (`POST /v1/crdt/replicas/{rid}/write`, `.../sync`, `GET .../state`). The
adapter maps `replica_write`/`replica_sync`/`replica_state` straight onto those
endpoints. **DinoMem is the only system under test with that surface**; every other
real system still raises `Unsupported` → `na`, and the in-process `FakeSUT`
reference also passes. The convergence guarantee is the core's CvRDT property suite
(`agentmem/supabase/functions/api/lib/crdt-merge.test.ts`: order-independence, the
CvRDT laws, no-lost-writes vs an independent brute force, partial-sync convergence,
and an LWW ablation), so a `pass` here is backed by an engine that is *empirically*
order-independent — not a machine-checked proof (DESIGN open question #2, resolved).

Setup: each of two replicas takes a **concurrent, conflicting** write on the same
key (`Owner` = Alice vs Bob, disjoint vclocks) plus one **distinct uncontended**
write (`Budget`, `Region`); replicas then gossip in reversed / randomised order.

| Metric | Status if… | Decided by |
|---|---|---|
| `S4.converge` | `pass` if both replicas reach the **same resolved state** regardless of sync order; `na` if no replica API. | `sorted(replica_state("R1")) == sorted(replica_state("R2"))`. |
| `S4.deterministic` | `pass` if the final state is identical across 10 seeded randomised sync orders (one reproducible winner for the contended key). | `len({final states}) == 1`. |
| `S4.lossless` | `pass` if **no write is dropped** — the contended key has exactly one surviving winner AND both distinct uncontended keys survive the merge (observable through the plain `state` API; an optional `replica_history` hook, when present, additionally confirms `≥ 4` ops retained). | `has(budget) and has(region) and one owner-winner [and len(replica_history()) >= 4]`. |
| `S4.converge_ms` (`info`) | always `info` (no pass/fail). | Wall-clock for one out-of-order sync round-trip over the concurrent ops. |

### S5 — Cross-workflow isolation (`s5_isolation.py`)

Requires `SCOPES`. 50 writes/workflow (env-scalable) across two workflows; a
workflow-A reader searches for each known workflow-B token.

| Metric | Status if… | Decided by |
|---|---|---|
| `S5.leakage_rate` | `pass` if the rate is **exactly 0.0%**; `na` if no `SCOPES`. | A leak is counted only when a returned hit's **content actually contains the workflow-B token** — not merely a non-empty top-k (a vector store always returns its k nearest, so "any hit" would false-positive). |

### S6 — Policy fidelity (`s6_policy.py`)

Requires `POLICIES`. For each policy the scenario configures it, then creates the
S1 conflict, then reads.

| Metric | Status if… | Decided by |
|---|---|---|
| `P.ignore.correct` | `pass` if the read returns **both** "friday" and "monday". | Keep-all semantics. |
| `P.timestamp_wins.correct` | `pass` if it returns "monday" and **not** "friday". | Most-recent wins. |
| `P.planner_wins.correct` | `pass` if it returns "friday" and **not** "monday". | Planner role wins. |
| `P.human_in_loop.correct` | `pass` if a conflict event was **surfaced** OR both facts are retained (i.e. NOT silently auto-resolved). | `surfaced or both`. |
| `P.human_in_loop.surfaced` | `pass` if `pending_events()` contains an event whose `type` starts with `"conflict"`. | The unambiguous HITL signal. |

All five record `na` if the SUT has no `POLICIES` capability.

### S7 — Operational metrics (`s7_operational.py`)

No capability requirement. Replays the committed `fixtures/s7_writes.jsonl`
workload (default 1000 writes + 500 searches, env-scalable) and measures, **all
as `info`** (no pass/fail):

`Op.write_mean_ms`, `Op.write_p50_ms`, `Op.write_p95_ms`, `Op.write_p99_ms`,
the matching `Op.search_*` percentiles, and `Op.write_$_per_1k` /
`Op.search_$_per_1k`. Cost is reported `N/A` when it is a server-side
subscription (`cost_observable = False`) rather than a misleading `$0`. Latency
is wall-clock around each op via `time.perf_counter()`; percentiles are computed
over the per-op samples in this run.

---

## 3. Determinism guarantees

These are what make a re-run reproduce the published numbers:

- **Fixed RNG seeds.** Every scenario that randomises (S4 sync orders seed `42`;
  S5 writes seed `5`; the S7 fixture generator seed `7`) uses a hard-coded seed.
- **Committed fixtures.** `fixtures/s7_writes.jsonl` is exactly 1000 lines and is
  committed; if absent it regenerates **deterministically** from the same seed, so
  the first run materialises an identical, committable fixture.
- **SUT-assigned timestamps, not sleeps.** Temporal scenarios (S2) query at the
  `created_at` the SUT returned for each write — never `time.sleep()` to "wait for
  T1". Settling waits on a *visibility condition*, not a fixed interval.
- **Pinned models, no `latest`.** Every embedding/LLM model string + its USD price
  lives in `dinomem_bench/models.py` (e.g. `text-embedding-3-small`,
  `gpt-4o-mini-2024-07-18`, `gemini-2.5-flash`, `claude-sonnet-4-6`). Adapters
  import the pinned string from there so the version and price can't drift apart.
- **Provenance recorded.** Each `runs/<id>/manifest.json` records the harness
  version, git sha, Python version, platform, and each SUT's version +
  capabilities; `compare.py` prints, per cell, which run it came from.
- **One re-run before `crash`.** The runner re-runs a scenario once on exception
  before recording `crash`, to suppress a single transient hosted-API blip.

What we **cannot** pin: a hosted SUT's server-side behaviour. If a vendor changes
its endpoint silently, our numbers move with it; we re-publish quarterly and note
drift (DESIGN §6).

---

## 4. Reproducing a run

The harness core + the reference `FakeSUT` are stdlib-only — no third-party deps,
no lock file:

```bash
pip install -e .                                   # core, stdlib-only
python3 -m dinomem_bench --sut fake --scenarios all   # the canonical full run
python3 -m dinomem_bench --list                       # SUTs + scenarios
python3 tests/test_smoke.py                            # smoke tests, no pytest needed
python3 -m dinomem_bench.compare                       # merge runs/ -> results/COMPARISON.md
```

A run writes a self-contained `runs/<run_id>/` directory: `manifest.json`,
`scenarios/<slug>.jsonl` (one line per metric), `timing.json`, `cost.json`,
`judgements.jsonl` (empty — no LLM judge), and a `summary.md` scorecard. `runs/`
is gitignored and published as a GitHub Release asset, not committed to git
history.

Real SUTs add their own optional extras + env (and config overrides — see
[`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`configs/`](./configs)):

```bash
# pgvector floor — needs Postgres+pgvector + OpenAI embeddings
DATABASE_URL=postgresql://… OPENAI_API_KEY=… \
  python3 -m dinomem_bench --sut pgvector --scenarios all   # extra: ".[pgvector]"

# pre-flight cost guard (op-counts × pinned prices; no live API call)
python3 -m dinomem_bench --sut pgvector --scenarios all --estimate-cost
```

A real (paid) run prices itself first from the pinned model prices and **aborts
before any SUT work** if the estimate exceeds `--max-usd` (default `30.0`).

---

## 5. Why no LLM-as-judge is a strength

A benchmark whose verdicts depend on an LLM is only as reproducible as that LLM's
weights, temperature, and availability — and, here, would invite the exact COI we
are trying to avoid (the maintainers also ship a Claude/Gemini-driven product).
Because every shipped assertion is a plain deterministic comparison, a third party
needs **zero judging-model access** to reproduce our pass/fail cells, and there is
no place for author discretion to creep in. The earlier `DESIGN.md §5.3` sketch of
a sparing Claude judge is **not used by any shipped scenario**; if one is ever
added, its prompt will be published in this section and every call logged to
`judgements.jsonl`.
