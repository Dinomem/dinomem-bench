# dinomem-bench

A reproducible benchmark for **multi-agent memory systems** — the gap LoCoMo, LongMemEval, and ConvoMem don't cover.

This repo is the methodology + harness + datasets, not a product. Read [`DESIGN.md`](./DESIGN.md) before running anything.

> ## ⚠️ Conflict of interest / integrity
>
> **DinoMem's maintainers build *and* run this benchmark, and DinoMem is one of the
> systems under test.** That is a real conflict of interest, so transparency is the
> whole point of this repo. Our mitigations:
>
> - **Published harness + assertions.** The deterministic assertions in the scenario
>   code *are* the judge — there is no LLM-as-judge to hide behind. Every metric's
>   exact predicate is documented in [`METHODOLOGY.md`](./METHODOLOGY.md).
> - **Provenance on every cell.** Run id, git sha, and pinned model versions are
>   recorded for each result so anyone can re-run and reproduce it.
> - **We report *every* metric — including the ones DinoMem fails or is N/A on.** The
>   matrix has an explicit *"Where DinoMem loses / is N/A"* section; see
>   [`results/COMPARISON.md`](./results/COMPARISON.md). (DinoMem **fails** S2 temporal.
>   On **S4 CRDT** it is now the *only* SUT that can run the scenario — its CRDT-V3
>   replica/sync API is drivable end-to-end — while every other real system stays
>   N/A; the committed matrix cell is regenerated from `runs/`, so it flips to ✅ on
>   the next live run, not by hand.)
> - **Black-box, public APIs only.** No system is tested through privileged internals.
> - **Competitors are invited to PR their own adapters / config overrides.** The
>   maintainers keep merge rights on *harness code only* — see
>   [`CONTRIBUTING.md`](./CONTRIBUTING.md) and [`configs/`](./configs).
>
> DinoMem is one SUT here, not the subject of this repo. Full disclosure: `DESIGN.md §9`.

## Why another benchmark

LoCoMo (Maharana et al., ACL 2024) and LongMemEval (ICLR 2025) measure **single-agent long-term memory** — does the model recall what was said earlier? Useful, but Letta has publicly argued these measure retrieval, not agent memory ([Letta blog, 2025](https://www.letta.com/blog/long-conversation-locomo)). And **no existing benchmark stresses multi-agent coordination on memory**: contradictory writes, scope leakage, CRDT convergence, policy enforcement.

`dinomem-bench` fills that gap. We test scenarios with **multiple agents writing and reading shared memory**, and score whether the system:

1. Surfaces or auto-resolves contradictions according to the user's policy
2. Enforces visibility scopes (private / team / global)
3. Converges to a consistent state under concurrent writes (CRDT property)
4. Returns the right answer at the right time (temporal validity)
5. Doesn't leak across workflows / orgs

We run the same scenarios against every shipped memory system (Mem0, Zep, Cognee, Supermemory, LangMem, raw pgvector, DinoMem) on the same hardware with the same LLM, and publish reproducible numbers.

## Status

**Running (v0.1).** The adapter interface, a reference `FakeSUT`, all seven
scenarios (S1–S7) with the metric names from [`DESIGN.md`](./DESIGN.md), the run
loop, and the output format are implemented and validated end-to-end. Real SUT
adapters (pgvector, DinoMem, Mem0, Zep, Cognee, Supermemory, LangMem) are present
and the cross-system results are committed at
[`results/COMPARISON.md`](./results/COMPARISON.md). See [`DESIGN.md`](./DESIGN.md)
for the methodology.

**v1 scope.** Bench v1 ships **S1–S7**, including **S4 (CRDT convergence)**.
DinoMem's CRDT **V3** now ships a real convergence engine + a black-box replica/sync
API (`POST /v1/crdt/replicas/{rid}/write`, `.../sync`, `GET .../state`), so the
harness drives S4 against DinoMem end-to-end and its convergence is property-tested
and empirically order-independent by the core's CvRDT property suite
([`agentmem/supabase/functions/api/lib/crdt-merge.test.ts`](../agentmem/supabase/functions/api/lib/crdt-merge.test.ts)).
**DinoMem is the only system under test with a drivable replica/sync API** — the
other real systems remain structurally **N/A** on S4, and the `FakeSUT` reference
also passes it.

## Running

The harness core + the reference `FakeSUT` are **stdlib-only**, so the canonical
one-command run needs zero third-party deps (no lock file, no `uv`, no Docker):

```bash
python3 -m dinomem_bench --sut fake --scenarios all   # canonical full run
python3 -m dinomem_bench --sut fake --scenarios s1,s4 # a subset
python3 -m dinomem_bench --list                        # SUTs + scenarios
python3 tests/test_smoke.py                             # smoke tests (no pytest needed)
```

### Cost estimate + budget guard

Before any real (paid) run, the harness prices the selected SUTs x scenarios from
**operation counts x pinned model prices** (`dinomem_bench/cost.py` +
`dinomem_bench/models.py`) — no live API call. Inspect it, or cap a run:

```bash
python3 -m dinomem_bench --sut fake --scenarios all --estimate-cost   # print table, exit
python3 -m dinomem_bench --sut pgvector --scenarios s7 --max-usd 30   # abort if est > $30
```

`--estimate-cost` prints a per-SUT/per-scenario + total USD table and exits without
running. A real run computes the same estimate first and **aborts before any SUT
work** if the total exceeds `--max-usd` (default `30.0`). In-process/flat-rate SUTs
(FakeSUT, hosted subscriptions) estimate to ~$0, so a fake run never aborts.

A run writes a self-contained `runs/<run_id>/` directory: `manifest.json`,
`scenarios/<slug>.jsonl` (one line per metric), `timing.json`, `cost.json`, and
a human-readable `summary.md` scorecard. `runs/` is gitignored (published as
release assets, per the design).

### Real SUT adapters

```bash
# pgvector floor — needs Postgres+pgvector + OpenAI embeddings
docker run -d --name amb-pg -e POSTGRES_PASSWORD=bench -e POSTGRES_DB=bench -p 5433:5432 pgvector/pgvector:pg16
DATABASE_URL=postgresql://postgres:bench@localhost:5433/bench OPENAI_API_KEY=... \
  python -m dinomem_bench --sut pgvector --scenarios all      # extra: psycopg[binary], openai

MEM0_API_KEY=...      python -m dinomem_bench --sut mem0 --scenarios all     # extra: mem0ai
DINOMEM_API_KEY=...  python -m dinomem_bench --sut dinomem --scenarios all # extra: httpx
```

Hosted SUTs with rate/quota limits can scale S7 down with `AMBENCH_S7_WRITES` /
`AMBENCH_S7_SEARCHES` (default stays the design's 1000/500); latency percentiles
are size-robust.

### Comparison matrix

```bash
python -m dinomem_bench.compare      # reads runs/ -> results/COMPARISON.md
```

`compare.py` merges multiple (incl. partial / re-run) `runs/` into one matrix:
for each (SUT, scenario) it uses the most recent run with real metrics and prints
provenance. **The current matrix is committed at [`results/COMPARISON.md`](./results/COMPARISON.md).**

### Headline (all 7 DESIGN systems)

> DinoMem is the Postgres-native memory layer for multi-agent systems — it runs
> entirely inside your Supabase/Postgres (no separate Redis, Neo4j, or Pinecone) and
> gives concurrent agents typed, auditable conflict resolution.

(DinoMem is one system under test here, not the subject of this repo — see the COI
disclosure in DESIGN §9.)

Different systems fill different coordination gaps — "best memory system" is a
category error (DESIGN §3):

- **S1 (contradiction detect + resolve): only DinoMem.** Every floor system
  (pgvector / mem0 / supermemory / langmem) and the graph systems (zep / cognee)
  are N/A — no conflict-surfacing/policy API.
- **S2 (temporal validity): only Zep.** It auto-invalidates a fact when a later
  one contradicts it (`invalid_at`), so `at_time` returns the right fact. DinoMem
  accepts `at_time` but returns both (gap); everyone else is N/A.
- **S3 scope / S5 isolation:** the verbatim floors pass cleanly (pgvector, langmem,
  + DinoMem). mem0 / supermemory **lose `S3.team_visible`** (content dedup/aggregation
  ignores scope changes). zep / cognee are N/A (graph-centric, no per-agent scope;
  cognee's zero-setup mode doesn't isolate at all — 100% leak — see its note).
- **S4 (CRDT): only DinoMem.** CRDT V3 ships a real op-based LWW-Register CvRDT
  engine behind a black-box replica/sync API, so the convergence test (concurrent
  conflicting writes → out-of-order gossip → converge to one deterministic,
  lossless state) runs end-to-end against DinoMem; the engine's convergence is
  property-tested in the core
  ([`crdt-merge.test.ts`](../agentmem/supabase/functions/api/lib/crdt-merge.test.ts)).
  No other hosted/self-host SUT exposes a drivable replica/sync API, so they stay
  N/A (the `FakeSUT` reference also passes).
- **S7 latency:** langmem / zep / pgvector ~300 ms · mem0 ~1.1 s · supermemory
  ~2.2 s · **cognee ~21 s** (add+cognify per write). DinoMem S5/S6/S7 await a
  Gemini-quota reset; its S6 also surfaced a backend 5xx under rapid policy writes.

The full per-metric matrix is committed at
[`results/COMPARISON.md`](./results/COMPARISON.md); each system's writeup is in
[`notes/`](./notes).

### DinoMem scope (non-goals)

For context on the system-under-test the maintainers build:

Non-goals (state explicitly; we are NOT building toward these):
- NOT Mem0-scale at 100M+ vectors per tenant.
- NOT a many-storage-backend abstraction (Postgres-only is the point).
- NOT best-in-class entity/relation extraction quality.
- NOT a general document-RAG ingestion pipeline.
- NOT procedural skill learning.

The defensible quadrant is single-substrate (Postgres-only) x CRDT conflict
handling — and as of CRDT **V3** the CRDT half is **shipped and measured** (a real
op-based LWW-Register CvRDT engine with an empirical convergence property suite in
the core, driven black-box by S4), not a roadmap item. We still describe it as
*measured/empirical* convergence, not a machine-checked formal proof.

### Adding a system under test

Implement `dinomem_bench.adapter.SUTAdapter` (the small `write` / `search` /
`check_conflicts` / `set_policy` / replica surface), declare its
`capabilities`, and register it in `dinomem_bench/suts/__init__.py`. Methods a
system can't support raise `Unsupported` → the affected metrics score `N/A`, not
a failure. `FakeSUT` (`dinomem_bench/suts/fake.py`) is the worked reference.

## License

[Apache-2.0](./LICENSE) (TBD)
