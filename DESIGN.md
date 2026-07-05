# Multi-Agent Memory Benchmark — Design

**Version:** 0.1 (harness running)
**Last updated:** 2026-06-14
**Status:** RUNNING. The harness is implemented and validated end-to-end against the
in-process reference `FakeSUT`; real-system adapters (pgvector, DinoMem, Mem0, Zep,
Cognee, Supermemory, LangMem) are present, and the cross-system results are committed
at [`results/COMPARISON.md`](./results/COMPARISON.md). Comments welcome via issues.

One-command run (stdlib-only core, no extras needed for the reference SUT):

```bash
python3 -m dinomem_bench --sut fake --scenarios all
```

**v1 scope:** ships **S1–S7**, including **S4 (CRDT convergence)**. DinoMem's CRDT
**V3** now ships a real convergence engine + a black-box replica/sync API
(`POST /v1/crdt/replicas/{rid}/write`, `.../sync`, `GET .../state`), so S4 is no
longer gated/roadmap for DinoMem: the harness drives it end-to-end through the
public API, and the convergence is property-tested and empirically order-independent
by the core's CvRDT property suite
([`agentmem/supabase/functions/api/lib/crdt-merge.test.ts`](../agentmem/supabase/functions/api/lib/crdt-merge.test.ts):
order-independence, the CvRDT laws, no-lost-writes vs an independent brute force,
partial-sync convergence, and an LWW ablation). **DinoMem is the only system under
test with a drivable replica/sync API**; the other real systems remain structurally
**N/A** on S4 (they expose no replica/vector-clock surface a convergence test can
drive), and the in-process `FakeSUT` reference still passes it too. See §4 S4 and §9
open question #2. (The S4-DinoMem matrix cell flips to ✅ on the next live bench run
against a deployed instance — the committed `results/COMPARISON.md` is regenerated
from `runs/` only.)

---

## 1. Motivation

Every published agent-memory benchmark today (LoCoMo, LongMemEval, ConvoMem, MemoryAgentBench, MemMachine, DMR) measures **one agent talking to one user across one long conversation**. The hard cases in production multi-agent systems are not retrieval — they are:

- Two agents writing contradictory facts and the system silently picking one.
- A planner's decision being overwritten by an executor.
- Memories leaking across workflows because the scoping API is opaque.
- Concurrent writes producing divergent state on different replicas.
- "What was true at T?" temporal queries breaking when the system only stores latest.

The Cemri et al. paper (arXiv:2503.13657) analysed 1,600+ multi-agent execution traces and found **36.9% of failures** were caused by agents ignoring, duplicating, or contradicting each other's work. Memory systems are the substrate where this either gets solved or compounded. No public benchmark currently scores systems on this dimension.

`dinomem-bench` is that benchmark.

### What this is not

- Not a replacement for LoCoMo / LongMemEval. We complement them; single-agent retrieval is still important.
- Not a leaderboard for marketing wins. We publish the methodology in full, including the cases where every system fails.
- Not a CRDT formalism paper. We measure operational properties (does the system converge?), not prove invariants.

---

## 2. Scope

### In

- Multi-agent **write contention** — two agents writing facts about the same entity.
- **Scope enforcement** — private / team / global / role-based access checks.
- **Conflict resolution policies** — `planner_wins`, `timestamp_wins`, `ignore`, `human_in_loop`.
- **Temporal queries** — `at_time` retrieval ("what did we believe last Tuesday?").
- **CRDT convergence** — out-of-order delivery, network partition simulation, replay.
- **Cross-workflow isolation** — does a write in workflow A leak into workflow B?
- **Cost & latency** — per-operation $ and ms, since systems differ wildly here.

### Out

- Single-agent long retrieval. Use LoCoMo / LongMemEval.
- Embedding model quality. We use the same embedding model across all SUTs where configurable.
- Streaming response quality.
- RAG over external documents.
- Anything requiring more than 1 hour of compute per full benchmark run (budget below).

---

## 3. Systems Under Test (SUT)

| System | Version | Hosted vs self-host | Embeddings | LLM for extraction |
|---|---|---|---|---|
| **DinoMem** | latest | hosted (default) | Gemini Embedding 2 | Gemini 2.5 Flash |
| **Mem0** | latest | hosted (free tier) + OSS self-host | OpenAI | gpt-4o-mini |
| **Zep** | latest | hosted | Zep default | Zep default |
| **Cognee** | latest | self-host (zero-infra: SQLite+LanceDB+Kuzu) | OpenAI | gpt-4o-mini |
| **Supermemory** | latest | hosted | Supermemory default | Supermemory default |
| **LangMem** | latest | self-host (LangGraph Postgres backend) | OpenAI | gpt-4o-mini |
| **pgvector baseline** | — | self-host | OpenAI | none (no extraction) |

The **pgvector baseline** is critical. It's just `INSERT` + cosine-similarity `SELECT TOP K`. If a benchmark scenario can be passed by pgvector alone, that scenario is not measuring memory-system value — it's measuring retrieval. We want our scenarios to **separate** memory systems from raw vector stores.

### What we will NOT report

- A single "winner" score. We report per-scenario, per-metric breakdowns. Different systems are good at different things; "best memory system" is a category error.
- Inferred internals (e.g., "Cognee uses Kuzu internally"). We treat all SUTs as black boxes via their public API.

---

## 4. Scenarios

Each scenario is a deterministic script: setup → operations → assertions. Scenarios are versioned (`v0.1.0`, etc.) so improvements don't invalidate prior runs.

### S1 — Contradictory writes (basic)

Two agents (`planner`, `executor`) in one workflow write contradictory facts about the same entity within 1 second of each other.

```
planner.write("Deadline is Friday.",  scope=team, workflow=wf-1, role=planner)
executor.write("Deadline is Monday.", scope=team, workflow=wf-1, role=executor)
```

**Metrics:**
- **C1.detected**: did the system surface the conflict on read? (Y/N)
- **C1.resolved**: under `planner_wins` policy, does retrieval return only the planner's fact? (Y/N)
- **C1.consistent**: do two parallel readers see the same fact? (Y/N)

### S2 — Temporal validity

Agent A writes fact F1 at T0. Agent A writes contradicting fact F2 at T1 (= T0 + 60s). Reader queries `at_time=T0` and `at_time=T1`.

**Metrics:**
- **T1.t0**: at T0, does retrieval return F1 only? (Y/N)
- **T1.t1**: at T1, does retrieval return F2 only? (Y/N)
- **T1.bitemporal**: does the system support `at_time` at all? (Y/N — many do not)

### S3 — Scope enforcement

Agent A writes a `private` memory. Agent B (different `agent_id`, same `workflow`) searches.

**Metrics:**
- **S3.isolated**: does B's search return zero hits? (Y/N)
- **S3.team_visible**: if A re-writes the same fact at `team` scope, does B now see it? (Y/N)
- **S3.cross_workflow**: does a workflow-B reader see any of workflow-A's facts? (must be N)

### S4 — Concurrent writes (CRDT)

Multiple replicas take **concurrent, conflicting** writes (the same key with
different values, disjoint vector clocks), plus a distinct uncontended key per
replica. Replicas then gossip in **reversed / randomised order**.

**Metrics:**
- **S4.converge**: do all replicas reach the same final state regardless of sync order? (Y/N — the CRDT convergence property)
- **S4.deterministic**: is the final state the same across 10 randomised sync orders, with a single reproducible winner for the contended key? (Y/N)
- **S4.lossless**: is no write dropped — the contended winner *and* each replica's distinct uncontended key all survive the merge (observable through the plain state API)? (Y/N)
- **S4.converge_ms** (`info`): wall-clock for one out-of-order sync round-trip over the concurrent ops — operational colour, not a correctness gate.

This is the headline differentiator, and as of CRDT **V3** it is a **measured**
guarantee for DinoMem, not a roadmap item. DinoMem ships a real op-based
LWW-Register CvRDT engine ([`agentmem/supabase/functions/api/lib/crdt-merge.ts`](../agentmem/supabase/functions/api/lib/crdt-merge.ts))
behind a black-box replica/sync API (`routes/crdt.ts`), and the engine's
convergence is property-tested in
[`agentmem/supabase/functions/api/lib/crdt-merge.test.ts`](../agentmem/supabase/functions/api/lib/crdt-merge.test.ts)
(order-independence, the CvRDT laws, no-lost-writes vs an independent brute-force
reference, partial-sync convergence, and an LWW ablation showing naive ts-only LWW
is order-sensitive / loses causal writes where the engine is not). The harness
drives that API end-to-end, so S4 passes for DinoMem. **It is the only system under
test that exposes a drivable replica/vector-clock API** — every other real system
remains `N/A` on S4 (no replica/sync surface to drive); the in-process `FakeSUT`
reference also passes. The property suite is an *empirical* convergence check, not a
machine-checked formal proof — we say "measured convergence", not "proven invariant".

### S5 — Cross-workflow isolation

Two workflows, three agents each, 50 writes per workflow. Reader in workflow A searches for content known to be in workflow B.

**Metrics:**
- **S5.leakage_rate**: % of workflow-A searches that surface workflow-B content (must be 0% for global-scope writes excluded; otherwise any leakage is a bug)

### S6 — Policy fidelity

Run S1 under each policy (`ignore`, `timestamp_wins`, `planner_wins`, `human_in_loop`) and assert the outcome matches the policy semantics.

**Metrics:**
- **P.<policy>.correct**: for each policy, does retrieval after conflict match the documented behaviour? (Y/N per policy)
- **P.human_in_loop.surfaced**: does the system emit a webhook / event for HITL? (Y/N)

### S7 — Operational metrics (cost + latency)

Run a synthetic workload — 1,000 writes + 500 searches over a 30-minute window — and measure:

**Metrics:**
- **Op.write_p50_ms**, **Op.write_p95_ms**
- **Op.search_p50_ms**, **Op.search_p95_ms**
- **Op.write_$_per_1k**: USD per 1,000 writes (extraction LLM + embedding + storage)
- **Op.search_$_per_1k**: USD per 1,000 searches (embedding + retrieval LLM if any)

Scenarios S1–S6 are correctness tests; S7 measures the operational envelope.

---

## 5. Methodology

### 5.1 Harness shape

Each SUT implements a small adapter interface:

```python
class SUTAdapter(Protocol):
    name: str
    version: str

    def setup(self) -> None: ...
    def teardown(self) -> None: ...

    def write(self, content: str, agent_id: str, scope: str, role: str | None,
              workflow_id: str | None) -> WriteResult: ...
    def search(self, query: str, agent_id: str, workflow_id: str | None,
               top_k: int = 5, at_time: datetime | None = None) -> list[Hit]: ...
    def check_conflicts(self, content: str, agent_id: str,
                        workflow_id: str | None) -> list[Conflict]: ...
    def set_policy(self, policy: str, workflow_id: str | None) -> None: ...
```

Scenarios drive `SUTAdapter` calls and assert outcomes. If an SUT can't implement a method (e.g., Mem0 has no concept of `at_time`), the adapter declares it `unsupported` and the scenario records `N/A`, not a failure.

### 5.2 Determinism

Each scenario is seeded with a fixed RNG seed. Inputs are pre-generated and committed to the repo. Two runs of the same scenario against the same SUT version should produce the same `<metric>: <value>` pairs.

### 5.3 LLM-as-judge — used sparingly

Scenarios that require semantic correctness (e.g., "did the system surface a meaningful conflict?") use **Claude Sonnet 4.6** as the judge. Each judgement is recorded with the full prompt + completion in `runs/<run_id>/judgements.jsonl` for audit. We do not use the SUT's own LLM as the judge.

### 5.4 Failure modes

A scenario can fail in three ways. We distinguish them:

- **Wrong answer**: SUT returned a result that violates the scenario's assertion. Counted as a metric failure.
- **Unsupported**: SUT's API doesn't support what the scenario needs. Counted as `N/A`, not a failure. (E.g., a system without temporal queries can't be scored on `T1.t0`.)
- **Crash**: SUT raised an exception, returned 500, or timed out (60s). Counted as `crash`. Re-run once before marking final.

---

## 6. Reproducibility

This is the most important property. Existing memory benchmarks publish numbers no one can reproduce because the harness ships with assumptions about API keys, container versions, etc.

### Hard requirements

- **One command run**: `python3 -m dinomem_bench --sut fake --scenarios all`. This is
  the canonical command — the harness core + the reference `FakeSUT` are stdlib-only,
  so it runs with **zero third-party deps and no lock file**. Real SUTs add their own
  optional extras (`pip install -e ".[pgvector]"`, etc.); select one with `--sut`.
  (There is no `uv`/`uv run`, `uv.lock`, or `Dockerfile` workflow — earlier drafts
  promised those; the shipped harness is plain `python3 -m dinomem_bench`.)
- **Pinned models**: every embedding/LLM model is pinned to a specific version string
  in [`dinomem_bench/models.py`](./dinomem_bench/models.py) (e.g.,
  `gpt-4o-mini-2024-07-18`, `text-embedding-3-small`) with a USD price attached; we
  never use `latest`. Adapters import the pinned string + dims from that registry.
- **Fixture data committed**: the 1,000 writes for S7 live in `fixtures/s7_writes.jsonl`
  (self-healing — regenerated deterministically if missing).
- **Budget cap**: a full run costs well under **$30** in API spend; this is enforced
  by a pre-flight estimator ([`dinomem_bench/cost.py`](./dinomem_bench/cost.py)) that
  prices the selected SUTs x scenarios from op-counts x the pinned model prices,
  *before any SUT work*. Inspect it with `--estimate-cost` (prints a per-SUT/per-
  scenario + total table and exits); a real run aborts if the estimate exceeds
  `--max-usd` (default `30.0`). In-process/flat-rate SUTs (FakeSUT, hosted
  subscriptions) estimate to $0, so a fake run never aborts.
- **No proprietary endpoints required** unless they're free-tier accessible (Mem0 free tier, Zep free tier, Supermemory free tier, etc.)

### What we don't do

- Reproduce hosted-service quirks. If Mem0's hosted endpoint changes silently, our numbers will change too. We pin SUT package versions but cannot pin their server-side behaviour. We re-publish on a quarterly cadence and note version drift.

---

## 7. Output Format

Each run produces a directory:

```
runs/2026-05-19-1234abcd/
├── manifest.json         # run id, git sha, sut versions, env hash
├── scenarios/
│   ├── s1_contradictory.jsonl    # per-trial result
│   ├── s2_temporal.jsonl
│   ├── ...
├── judgements.jsonl      # every LLM-as-judge call
├── cost.json             # $ per SUT per scenario
├── timing.json           # latency histograms
└── summary.md            # human-readable summary (auto-generated)
```

A `compare.py` script reads multiple `runs/` and produces a comparison matrix in Markdown — that's the artifact the blog post / paper consumes.

---

## 8. Comparison-Set Inclusion Rules

To prevent gerrymandering:

- A system is "included" if it has a public Python or TypeScript client on PyPI / npm, OR a stable HTTP API + an OpenAPI spec.
- We **do not** include systems we have no way to test (closed-source enterprise SaaS without free tier).
- We **do** include unfunded / smaller systems (LangMem, raw pgvector) as floors.
- We **do not** exclude DinoMem from any scenario it can technically run, even if we expect it to fail.

If a system was contacted for a free tier or API key and the maintainer declined, that's documented in `STATUS.md` per SUT with the request thread.

---

## 9. Open Questions Before Implementation

These should be resolved before coding begins. Track in GitHub issues with `design` label.

1. **Embedding model parity** — should every SUT use OpenAI's `text-embedding-3-small`, or each SUT's default? Different choices yield different absolute numbers but the same *relative* ordering. Default proposal: **each SUT's default**, since that's what a real user gets out of the box. Document the choice in every report.

2. **Concurrent-write simulation** — can we actually exercise CRDT behaviour against hosted services? **Resolved.** We run S4 only against systems that expose a drivable replica/vector-clock API, scoring everything else `N/A`. As of CRDT **V3**, DinoMem exposes exactly such an API (`POST /v1/crdt/replicas/{rid}/write`, `.../sync`, `GET .../state`, backed by a property-tested CvRDT engine), so S4 is drivable end-to-end against it and is no longer `N/A` for DinoMem. **It remains the only SUT with that surface** — every other real system is still `N/A` on S4. The convergence guarantee is the core's empirical CvRDT property suite (`crdt-merge.test.ts`), not a marketing claim.

3. **LLM judge bias** — using Claude as the judge of a benchmark in which Claude is a possible production user. Default proposal: **also run a Gemini 2.5 Flash judge in parallel** for triangulation; flag any case where they disagree.

4. **Scenario depth vs breadth** — 7 scenarios above. Should we add more (e.g., adversarial prompt injection through memory writes)? Default proposal: **freeze v0.1 at S1–S7, add adversarial in v0.2**.

5. **Run cadence** — quarterly? Default proposal: **quarterly + on major version bump of any SUT**.

6. **Hosting** — runs publish to GitHub releases as artifacts, with a static HTML viewer in the repo. No external dashboard at v0.1.

7. **Conflict-of-interest disclosure** — DinoMem maintainers run the benchmark. We disclose this prominently in every report. Long-term mitigation: invite competitors to PR their own adapters (we keep merge rights on harness code only).

---

## 10. Implementation Plan

Status: the harness and all adapters below are **implemented**. What remains is
broader real-system result coverage (some `results/COMPARISON.md` cells are still
`N/A` pending API quota, and the S4-DinoMem cell flips to ✅ on the next live run
against a deployed CRDT-V3 instance) — not harness work.

1. **Harness skeleton, SUT adapter interface, run loop, output format — done.** The
   `SUTAdapter` contract, the run loop (fresh SUT per scenario, one re-run on
   exception, self-contained `runs/<id>/` output), and the `FakeSUT` reference are
   implemented and validated end-to-end by `tests/test_smoke.py`.
2. **Adapters for DinoMem + pgvector baseline + LangMem — done.** All seven scenarios
   (S1–S7) are implemented. S4 (CRDT) is drivable end-to-end against DinoMem via its
   CRDT-V3 replica/sync API (the only SUT with that surface); every other real system
   is `N/A` on S4 — see §4.
3. **Mem0 + Zep + Cognee + Supermemory adapters — done.** All seven scenarios are
   implemented; the cross-system matrix is committed at `results/COMPARISON.md`.
4. **Cost tracking + comparison tooling — done.** Pre-flight cost estimation
   (`--estimate-cost` / `--max-usd`, `dinomem_bench/cost.py` + the pinned
   `dinomem_bench/models.py` registry) and the `compare.py` matrix generator are
   implemented. Remaining: fill the `N/A` real-system cells as quota allows, and the
   blog/paper draft.

---

## 11. Success Criteria

We will consider v0.1 a success if:

- A reader who has never used any of these systems can run `dinomem-bench` end-to-end with one command and produce the same numbers we published.
- We can defensibly answer "how does your system perform on contradiction handling vs Mem0?" with a specific scenario number and a link to the trial JSONL.
- The methodology section survives review by at least one independent researcher without major methodological objections.

Not a success criterion: DinoMem winning every metric. We expect to lose some (e.g., latency vs Mem0's hosted, which has a head start on infrastructure).

---

## 12. Related Work

- **Cemri et al. (2026)** — arXiv:2503.13657 — *Why Do Multi-Agent LLM Systems Fail?* — origin of the 36.9% coordination-failure stat. Closest in spirit to our motivation.
- **CodeCRDT** — arXiv:2510.18893 — CRDT semantics for multi-agent code editing. Methodologically analogous; we adapt the convergence-test framing.
- **Semantic Consensus** — arXiv:2604.16339 — Process-aware conflict detection in enterprise multi-agent systems. Informs S6 (policy fidelity).
- **LoCoMo** — Maharana et al., ACL 2024 — single-agent long memory.
- **LongMemEval** — ICLR 2025 — single-agent long memory.
- **Mem0 paper** — ECAI 2025, arXiv:2504.19413 — broad memory-system comparison, single-agent focused.
- **Zep paper** — arXiv:2501.13956 — temporal knowledge graph + Graphiti.

---

## 13. Changelog

- **2026-07-05** — DinoMem hosted endpoint is **fully live** (Supabase project
  restored; no longer paused free-tier). Fincil app-level dogfood run completed
  (`/mnt/308E51BA8E517974/fincil-remastered/notes/dinomem-test/`): S1 conflict
  detection + `planner_wins` resolution confirmed on live traffic; P1 factKey
  bi-temporal versioning confirmed structural; P2 immutable receipts confirmed (8
  receipts / 3 debates; `reader_agent` = search `agentId`). S4 (CRDT V3) adapter
  is ready and driving the deployed endpoint — first live bench run pending (the
  committed `results/COMPARISON.md` N/A cells flip to ✅ once that run is recorded).
  **Key operational finding**: `factKeyPrefix` does **not** filter on the live
  endpoint — `workflowId` is the only reliable per-user isolation primitive. S7
  search p50 (891ms) is without `rerank:true`; with rerank enabled expect 2.5–6.3s
  per search call (measured in the Fincil dogfood). S2 temporal gap narrowed but not
  closed: factKey supersession (P1) works; `atTime` returning a single fact per
  validity window still needs a `timestamp_wins`-policy repro.
- **2026-06-14** — S4 (CRDT convergence) is now live for DinoMem. CRDT V3 ships a
  real op-based LWW-Register CvRDT engine + a black-box replica/sync API; the
  DinoMem adapter advertises `VECTOR_CLOCK` and drives it, and S4 was hardened to
  assert convergence + a deterministic winner + API-observable losslessness. DinoMem
  is the only SUT with a drivable replica API; the others remain `N/A`. Closes open
  question #2.
- **2026-05-19** — v0.1 design. Initial draft.
