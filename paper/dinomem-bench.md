# dinomem-bench: A Reproducible Benchmark for Multi-Agent Memory Coordination

**Authors.** Aneesh (devsforfun) et al.
**Version.** v0.1 working draft — 2026-06-13.
**Artifacts.** Code, scenarios, and all raw run logs: https://github.com/DinoMem/dinomem-bench

> **Author note (delete before submission):** this is a complete first draft in
> Markdown for editing; convert to LaTeX (e.g. `pandoc`) for arXiv. All numbers are
> from committed runs (`results/COMPARISON.md`). **Verify every external citation's
> arXiv ID/year against the source before submission** — the related-work IDs below
> are carried from the project's design RFC and some are placeholders.

---

## Abstract

Existing agent-memory benchmarks (LoCoMo, LongMemEval, ConvoMem) evaluate a single
agent recalling information from one long conversation. We argue this misses the
dominant failure mode of *multi-agent* systems, where memory is shared and the hard
problems are coordination: contradictory writes, temporal validity, scope leakage,
concurrent-write convergence, and conflict-resolution policy. We introduce
**dinomem-bench**, a reproducible benchmark of seven deterministic scenarios
(S1–S7) that isolate these properties, and evaluate seven shipped memory systems
(DinoMem, Mem0, Zep, Cognee, Supermemory, LangMem, and a raw pgvector baseline)
behind a uniform adapter interface, with an in-process reference implementation to
validate the scenarios themselves. We report per-scenario, per-metric results — not
a single score — and find the capability space is sharply non-uniform: contradiction
detection and resolution policies are provided by exactly one system; bitemporal
"what was true at T?" retrieval by exactly one (a different) system; concurrent-write
CRDT convergence is *drivable in exactly one* system — DinoMem, which ships an
op-based LWW-Register CvRDT engine (with property-tested, empirically order-independent
convergence) behind a black-box replica/sync API, the only such surface among the
systems under test, while every other system stays N/A on that axis for lack of a
replica API (the live cross-system S4 run awaits a deployed instance);
and a raw vector store matches the managed systems on every property that does not
require coordination machinery. Beyond the grid, the act of running the benchmark
surfaced reproducible operational failures (LLM-quota-coupled 5xx errors, silent
content deduplication that drops scope changes, ~50s indexing latencies, and a
configuration in which one system enforces no isolation at all). We release the
harness, scenarios, and complete run logs, and we disclose prominently that the
benchmark's authors also build one of the systems under test.

---

## 1. Introduction

Large-language-model agents increasingly operate in groups — planners, executors,
critics, tool-runners — that read and write a shared memory. When such a system
fails, it is usually not because a model forgot a fact. Cemri et al. built the
**MAST failure taxonomy** from 1,600+ multi-agent traces across 7 frameworks (41–86.7%
failure rates), with **inter-agent misalignment** — agents ignoring, duplicating, or
contradicting one another's work — as one of three top-level failure categories
[cemri2025mast]; a related study attributes **~79% of multi-agent failures** to
specification and coordination issues rather than model capability [acharya2026semconsensus].
Memory is the substrate on which that coordination either succeeds or compounds into failure.

Yet the benchmarks the field cites — LoCoMo [maharana2024], LongMemEval
[longmemeval2025] — measure single-agent long-context recall. They answer "can the
model retrieve what was said?", not "when two agents disagree about the same entity,
what does the system do?" These are different questions, and the second is the one
that breaks production multi-agent apps.

We close that gap with **dinomem-bench**: a benchmark whose scenarios are written
to *separate memory systems from vector stores* along coordination axes. Our
contributions:

1. **Seven coordination scenarios (S1–S7)** with precise, deterministic
   assertions: contradiction detection/resolution, temporal validity, scope
   enforcement, CRDT convergence, cross-workflow isolation, policy fidelity, and an
   operational (latency/cost) envelope (§3).
2. **A uniform black-box adapter interface** plus an in-process **reference
   implementation** that passes all scenarios, demonstrating the assertions are
   satisfiable and sound; and a principled distinction between *wrong answer*,
   *unsupported* (N/A), and *crash* (§3.4).
3. **An evaluation of seven shipped systems** under pinned models and committed
   fixtures, reported as a per-metric matrix rather than a leaderboard (§6).
4. **Qualitative operational findings** that the runs exposed — failure modes a
   static scorecard would miss (§7).
5. **A fully reproducible release** (one-command runs, committed raw logs,
   provenance) and an explicit conflict-of-interest disclosure (§5, §10).

Our central empirical claim is deliberately anti-climactic: **there is no "best"
multi-agent memory system.** Different systems provide disjoint coordination
capabilities, several provide none beyond a vector store, and one important property
(concurrent-write CRDT convergence) is *drivable in only one* shipping product:
DinoMem exposes a black-box replica/sync API over a property-tested CvRDT engine,
while every other system stays unverifiable on that axis for lack of any replica
surface a convergence test can drive.

## 2. Related Work

**Single-agent memory benchmarks.** LoCoMo [maharana2024] and LongMemEval
[longmemeval2025] evaluate long-term recall in extended single-agent dialogues. The
Mem0 system paper [mem0_2025] compares memory systems primarily on single-agent
retrieval quality and cost. Letta has argued such conversation benchmarks measure
retrieval rather than agentic memory [letta2025]. We complement, not replace, these:
single-agent recall remains important; we add the orthogonal multi-agent dimension.

**Temporal knowledge graphs.** Zep/Graphiti [zep2025] maintain bitemporal facts with
validity intervals; our S2 directly exercises that capability and our S6 the
conflict-policy literature.

**Multi-agent coordination and CRDTs.** Cemri et al. [cemri2026] motivate the
coordination-failure framing. CodeCRDT [codecrdt2025] adapts convergence testing to
multi-agent code editing; we borrow its order-independence framing for S4. Work on
process-aware conflict detection in enterprise multi-agent systems [semconsensus2026]
informs S6's policy taxonomy.

**Agent memory architectures.** MemGPT [packer2023] frames the LLM as an operating
system with paged memory; it is a memory *architecture* rather than a benchmark, and
is representative of the systems whose coordination properties we measure.

## 3. Benchmark Design

### 3.1 Design principles

- **Deterministic.** Each scenario is a fixed setup → operations → assertions
  script with committed inputs; two runs against the same system version produce the
  same metric values.
- **Black-box.** Systems are accessed only through their public API; we do not
  inspect or assume internals.
- **Separation over difficulty.** Scenarios are designed to *distinguish* a memory
  system from a raw vector store. A control baseline (pgvector) is included
  precisely so that any scenario it passes is recognized as not measuring
  memory-system value.
- **Honest non-support.** A system that lacks the API a scenario needs scores
  **N/A**, never a failure.

### 3.2 The adapter interface

Every system implements a small interface: `write(content, agent_id, scope, role,
workflow_id)`, `search(query, agent_id, workflow_id, top_k, at_time)`, and optional
`check_conflicts`, `set_policy`, and a replica/vector-clock surface for S4. Methods a
system cannot support raise `Unsupported`, which the harness records as N/A. Adapters
are ~100 lines; we invite system authors to contribute or correct their own.

### 3.3 Scenarios

- **S1 — Contradictory writes.** Two agents (`planner`, `executor`) write conflicting
  facts about one entity. Metrics: `detected` (is the conflict surfaced on read?),
  `resolved` (under `planner_wins`, does retrieval return only the planner's fact?),
  `consistent` (do parallel readers agree?).
- **S2 — Temporal validity.** Agent writes F1 at T0, contradicting F2 at T1. Metrics:
  `t0` (at_time=T0 returns F1 only), `t1` (at_time=T1 returns F2 only), `bitemporal`
  (is `at_time` supported at all?).
- **S3 — Scope enforcement.** A writes a `private` memory; B (different agent, same
  workflow) searches. Metrics: `isolated` (B sees nothing), `team_visible` (after A
  re-writes at `team`, B sees it), `cross_workflow` (a different-workflow reader sees
  nothing).
- **S4 — CRDT convergence.** Two replicas take conflicting writes with disjoint vector
  clocks, then sync in reversed/randomized order. Metrics: `converge` (replicas reach
  the same state), `deterministic` (same final state across 10 sync orders),
  `lossless` (both writes retained in history).
- **S5 — Cross-workflow isolation.** Two workflows, multiple agents, many writes each;
  a workflow-A reader searches for workflow-B content. Metric: `leakage_rate` (must be
  0% for non-global writes).
- **S6 — Policy fidelity.** Run the S1 conflict under each policy — `ignore`,
  `timestamp_wins`, `planner_wins`, `human_in_loop` — and assert retrieval matches the
  documented semantics; for HITL, assert the conflict is *surfaced* rather than
  silently auto-resolved.
- **S7 — Operational envelope.** A synthetic workload measuring write/search latency
  percentiles and per-operation cost.

### 3.4 Result taxonomy

We distinguish three non-pass outcomes (after Cemri's failure-mode discipline):
**wrong answer** (assertion violated → fail), **unsupported** (no such API → N/A,
not a failure), and **crash** (5xx/exception/timeout → re-run once before recording).
This separation is essential: conflating "can't do X" with "did X wrong" produces
misleading leaderboards.

### 3.5 Reference implementation

An in-process `FakeSUT` implements correct semantics for all scenarios (scopes,
conflict detection, all four policies, bitemporal validity, and a vector-clock CRDT).
It passes every correctness metric, which validates that the scenarios are
satisfiable and the assertions are sound — a check absent from most benchmarks.

## 4. Systems Under Test

| System | Access | Embeddings / extraction | Notes |
|---|---|---|---|
| DinoMem | hosted | Gemini | conflict API + policies; authors' system (§10) |
| Mem0 | hosted (free tier) | OpenAI | LLM dedup on write |
| Zep | hosted (free tier) | Zep default | temporal knowledge graph (Graphiti) |
| Cognee | self-host | OpenAI | knowledge graph; SQLite+LanceDB+Kuzu |
| Supermemory | hosted (free tier) | default | first-party SDK |
| LangMem | self-host | OpenAI | LangGraph store + semantic index |
| pgvector | self-host | OpenAI | **baseline/control**: INSERT + cosine top-k |
| *FakeSUT* | in-process | none | *reference, not under comparison* |

Embeddings follow each system's default (the real out-of-box experience); the choice
is documented per system. Models are pinned to version strings; no `latest`.

## 5. Experimental Setup & Reproducibility

The harness runs with one command per system (`python -m dinomem_bench --sut <name>
--scenarios all`) and emits a self-contained `runs/<id>/` directory: a manifest
(run id, versions, environment), per-scenario JSONL (one line per metric), latency
and cost JSON, and a generated summary. `compare.py` merges multiple runs into the
cross-system matrix with full provenance (which run each cell came from). Run
artifacts are committed; the comparison matrix is at `results/COMPARISON.md`.

Hosted systems with low free-tier quotas were run at reduced operation counts for
S5/S7 via documented environment knobs; latency percentiles are robust to the smaller
N. Where a system's pipeline is asynchronous (indexing/extraction), the harness waits
for index-visibility before assertions rather than using fixed sleeps.

## 6. Results

The complete matrix (✅ pass · ❌ fail · — N/A · ℹ️ measurement):

| Scenario / metric | pgvector | mem0 | zep | cognee | supermemory | langmem | **DinoMem** |
|---|---|---|---|---|---|---|---|
| S1 detected | — | — | — | — | — | — | **✅** |
| S1 resolved | — | — | — | — | — | — | **✅** |
| S1 consistent | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| S2 t0 | — | — | **✅** | — | — | — | ❌ |
| S2 t1 | — | — | **✅** | — | — | — | ❌ |
| S3 isolated | ✅ | ✅ | — | — | ✅* | ✅ | ✅ |
| S3 team_visible | ✅ | ❌ | — | — | ❌* | ✅ | ✅ |
| S3 cross_workflow | ✅ | ✅ | — | — | ✅* | ✅ | ✅ |
| S4 converge/det/lossless | — | — | — | — | — | — | —‡ |
| S5 leakage_rate | 0% | 0% | — | —† | 0%* | 0% | 0% |
| S6 policy×4 + surfaced | — | — | — | — | — | — | **✅** |
| S7 write p50 (ms) | 307 | 1143 | 305 | 20965 | 2222 | 303 | 1005 |
| S7 search p50 (ms) | 309 | 507 | 302 | 1919 | 1870 | 304 | 892 |

<sub>\* Supermemory's scope cells are confounded (§7). † Cognee's zero-setup mode
enforces no isolation (§7). ‡ DinoMem is the only system whose S4 convergence is
*drivable* (it ships a replica/sync API over a property-tested CvRDT engine); the cell
stays — until a live cross-system run against a deployed instance is recorded (§6, §10).</sub>

**Per-scenario analysis.**

- **S1 (contradiction).** DinoMem is the only system with both a conflict-detection
  API and policy-based resolution (it blocked the executor's conflicting write under
  `planner_wins` with a high-severity conflict description). No other system exposes
  a conflict-surfacing API. Mem0's write-time LLM deduplication does not resolve the
  contradiction — we verified the stale and updated values coexist.
- **S2 (temporal).** Zep is the only system to answer point-in-time queries
  correctly: it extracts facts with validity intervals and auto-invalidates the
  superseded fact (`invalid_at = T1`). DinoMem accepts an `at_time` parameter but
  returns both facts (a genuine gap). All others lack temporal queries entirely.
- **S3/S5 (scope, isolation).** These are expressible as filter predicates, so the
  baselines pass — confirming they do not differentiate memory systems from vector
  stores. The informative split is intra-tier: **verbatim stores (pgvector, LangMem,
  DinoMem) preserve a re-scoped fact; dedup/aggregating stores (Mem0, Supermemory)
  silently drop the scope change.**
- **S4 (CRDT).** N/A for every shipping system *except* DinoMem. DinoMem ships an
  op-based LWW-Register CvRDT engine behind a black-box replica/sync API
  (`replica_write` / `sync` / `state`), so it is the **only** system under test whose
  convergence the black-box test can drive end-to-end; every other system stays N/A
  for lack of a replica surface. The engine's convergence is **property-tested and
  empirically order-independent** in the core (`agentmem/supabase/functions/api/lib/
  crdt-merge.test.ts`, 8/8: order-independence across shuffles, the CvRDT laws —
  commutativity, associativity, idempotence — no-lost-writes vs an independent
  brute-force reference, partial out-of-order sync convergence, and a CRDT-vs-naive-LWW
  ablation). This is a property-test suite, **not** a machine-checked proof. We have
  not yet recorded a *live* cross-system S4 head-to-head against a deployed instance,
  so we make no *measured* S4 benchmark-win claim: DinoMem's S4 cell is reported as
  engine-property-tested + adapter-ready and flips to ✅ only once a live run lands in
  `runs/` (never hand-edited). The reference implementation also passes (§3.5).
- **S6 (policy).** DinoMem satisfies all four policies to spec; no other system
  ships conflict policies.
- **S7 (latency).** A ~70× spread: LangMem/Zep/pgvector ≈ 300 ms; DinoMem/Mem0 ≈
  1 s; Supermemory ≈ 2.2 s; Cognee ≈ 21 s/write (per-write LLM graph extraction).

## 7. Operational Findings

Static metrics understate what running the systems revealed:

- **LLM-quota coupling (DinoMem).** Conflict detection/extraction is backed by a
  generative model (Gemini); under a daily free-tier quota it returned `500` rather
  than degrading gracefully, and we observed a `500` under near-simultaneous policy
  writes. S6 completed only after provisioning fresh model quota on the backend — an
  honest demonstration of operational fragility in the authors' own system.
- **Dedup that drops scope (Mem0, Supermemory).** Re-writing identical content at a
  wider scope returns the original record's identity (Mem0) or aggregates to one
  memory (Supermemory), losing the scope change — the S3 `team_visible` failure.
- **Indexing latency and recall (Supermemory).** ~50 s per-document indexing, and its
  free-tier memory search did not reliably retrieve short factual writes — so its
  scope passes largely reflect empty results and are reported as confounded.
- **Isolation depends on configuration (Cognee).** In its zero-setup mode (access
  control disabled), search queries the global graph and leaked 100% across
  workflows; isolation requires its multi-tenant layer.
- **Correct-but-slow extraction (Zep).** Asynchronous (~50 s) fact extraction, but the
  only system to deliver temporal validity.

## 8. Discussion

The results refute a one-dimensional reading of "memory system." Coordination
capabilities are **disjoint across vendors**: contradiction handling (DinoMem),
temporal validity (Zep), and policy enforcement (DinoMem) are each provided by one
system, and several "memory systems" provide nothing a vector store does not. Two
implications follow. First, **buyers should select by the specific coordination
property their multi-agent application requires**, and verify the vendor even exposes
an API for it. Second, **a raw `pgvector` table is a strong, cheap baseline** at
modest scale and faithful-retrieval needs — the managed premium is justified only by
the coordination axes above.

## 9. Threats to Validity

- **Statistical.** Most correctness cells are single deterministic runs; S7 uses
  small N on quota-limited hosted systems (latency percentiles are N-robust, but
  tail estimates are coarse). Absolute latencies are environment- and tier-bound.
- **Construct.** Several systems store no scope label, so scope is emulated in the
  adapter; S3/S5 therefore partly measure the adapter. We mark such cells.
- **Coverage.** S4 is untestable as a black box for every hosted system *except*
  DinoMem, whose replica/sync API the convergence test can drive; for the others the
  CRDT dimension is currently unmeasured rather than failed. For DinoMem, the engine's
  convergence is property-tested in the core, but the cross-system *live* S4 run is
  pending a deployed instance, so we report it as engine-tested + adapter-ready rather
  than a measured head-to-head win.
- **Free-tier artifacts.** Quotas, indexing lag, and search recall on free tiers may
  differ from paid deployments; we document the tier per system.
- **Versioning.** Hosted backends can change server-side behavior we cannot pin; we
  pin client/package versions and re-publish on a cadence, noting drift.

## 10. Conflict of Interest

The authors develop **DinoMem**, one of the seven systems under test, and DinoMem
attains the only passes on S1 and S6 (its *shipped* conflict policies —
`planner_wins` / `timestamp_wins` / `human_in_loop`), and is also the only system that
exposes a drivable replica/sync API on S4. Because we both build and benchmark the one
S4-capable system, that result demands the most scrutiny, so we state its limits
precisely. DinoMem ships an op-based LWW-Register CvRDT engine whose convergence is
**property-tested and empirically order-independent** in the core (order-independence
across shuffles, the CvRDT laws, no-lost-writes vs an independent brute-force reference,
partial out-of-order sync convergence, and a CRDT-vs-naive-LWW ablation) — a
property-test suite, **not** a machine-checked proof, so we claim *property-tested
convergence*, not *proven* or *guaranteed*. We have **not** yet run a live cross-system
S4 head-to-head against a deployed instance, so we claim no *measured* S4 benchmark
win: DinoMem's S4 cell is reported as engine-property-tested + adapter-ready and flips
to a measured pass only when a live run is recorded. The honest asymmetry is that
DinoMem is uniquely *drivable* on S4 (it alone ships the replica surface), while every
other system is N/A there for lack of one. We mitigate as
follows: (i) this statement is prominent; (ii) we report DinoMem's **gap** (S2) and
that its S4 result is engine-tested-but-not-yet-a-live-measured-win in the same table; (iii) we document an
operational failure in our own system (§7); (iv) every scenario is a public,
deterministic script and every result links to a raw trial log, so any reader can
reproduce or refute; (v) adapters are open to PRs from competing vendors, who may
contribute or correct their own. We do not report a single aggregate score.

## 11. Conclusion & Future Work

dinomem-bench reframes memory evaluation from single-agent recall to multi-agent
coordination, and finds the capability landscape sharply differentiated and, on one
axis (CRDT convergence), drivable in only one shipping product — DinoMem, which alone
exposes a replica/sync API over a property-tested CvRDT engine, while the rest remain
unverifiable for lack of any replica surface. The S4 harness already drives that API;
v0.2 will: record the live cross-system S4 head-to-head against a deployed instance
(so the grid cell can flip from engine-tested to measured); tighten
per-operation cost instrumentation; increase N with seeds for confidence intervals;
and add an adversarial scenario (prompt injection via memory writes). We invite the
community to run the harness, contribute adapters, and challenge the methodology.

## References

*(IDs carried from the project design RFC — verify before submission.)*

- [cemri2026] Cemri et al. *Why Do Multi-Agent LLM Systems Fail?* arXiv:2503.13657.
- [codecrdt2025] *CodeCRDT: CRDT semantics for multi-agent code editing.* arXiv:2510.18893.
- [semconsensus2026] *Semantic Consensus: process-aware conflict detection in enterprise multi-agent systems.* arXiv:2604.16339.
- [maharana2024] Maharana et al. *LoCoMo: Evaluating Long-Term Conversational Memory.* ACL 2024.
- [longmemeval2025] *LongMemEval.* ICLR 2025.
- [mem0_2025] *Mem0.* ECAI 2025, arXiv:2504.19413.
- [zep2025] *Zep: a temporal knowledge graph architecture for agent memory.* arXiv:2501.13956.
- [packer2023] Packer et al. *MemGPT: Towards LLMs as Operating Systems.* arXiv:2310.08560.
- [letta2025] Letta. *Long conversation ≠ LoCoMo.* Blog, 2025.
