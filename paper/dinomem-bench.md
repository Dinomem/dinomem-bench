# dinomem-bench: A Reproducible Benchmark for Multi-Agent Memory Coordination

**Authors.** Aneesh (devsforfun) et al.
**Version.** v0.2 working draft — 2026-07-06 (live July runs: S4 measured, S2 via factKey, full S7 distributions).
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
"what was true at T?" retrieval is answered correctly by exactly two systems via
*opposite contracts* (automatic fact invalidation vs. caller-keyed versioning);
concurrent-write CRDT convergence is *measurable in exactly one* system — DinoMem,
whose op-based LWW-Register CvRDT engine we drove live through its black-box
replica/sync API: replicas receiving concurrent conflicting writes under
out-of-order gossip converged to one deterministic, lossless state across 10
delivery orders (~1.5 s per sync round-trip), while every other system stays N/A on
that axis for lack of a replica API a convergence test can drive; and a raw vector
store matches the managed systems on every property that does not require
coordination machinery. Beyond the grid, the act of running the benchmark surfaced
reproducible operational failures (LLM-quota-coupled 5xx errors, silent content
deduplication that drops scope changes, ~50s indexing latencies, a documented
filter parameter that performs no filtering, and a configuration in which one
system enforces no isolation at all). We additionally validate the grid's findings
at application level in a production-shaped multi-agent app, where bi-temporal
supersession and per-read audit receipts were observed end-to-end. We release the
harness, scenarios, and complete run logs, and we disclose prominently that the
benchmark's authors also build one of the systems under test — which, in the
current runs, passes every correctness metric; the conflict-of-interest section
states exactly how each such cell is conditioned.

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
   provenance) and an explicit conflict-of-interest disclosure (§5, §11).

Our central empirical claim is deliberately anti-climactic: **there is no "best"
multi-agent memory system.** Different systems provide disjoint coordination
capabilities, several provide none beyond a vector store, and one important property
(concurrent-write CRDT convergence) is *measurable in only one* shipping product:
DinoMem exposes a black-box replica/sync API over a property-tested CvRDT engine —
and the live S4 run converged deterministically and losslessly — while every other
system stays unverifiable on that axis for lack of any replica surface a
convergence test can drive.

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
  (is `at_time` supported at all?). Each system gets its native temporal mechanism:
  systems advertising a fact-versioning capability receive a stable fact key on both
  writes; systems with automatic invalidation need no hint. The contract difference
  is reported, not hidden (§6).
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
| DinoMem | hosted | Gemini | conflict API + policies; authors' system (§11) |
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
| S2 t0 | — | — | **✅** | — | — | — | **✅**‡ |
| S2 t1 | — | — | **✅** | — | — | — | **✅**‡ |
| S3 isolated | ✅ | ✅ | — | — | ✅* | ✅ | ✅ |
| S3 team_visible | ✅ | ❌ | — | — | ❌* | ✅ | ✅ |
| S3 cross_workflow | ✅ | ✅ | — | — | ✅* | ✅ | ✅ |
| S4 converge/det/lossless | — | — | — | — | — | — | **✅ (live)** |
| S5 leakage_rate | 0% | 0% | — | —† | 0%* | 0% | 0% |
| S6 policy×4 + surfaced | — | — | — | — | — | — | **✅** |
| S7 write p50 (ms) | 470 | 1082 | 300 | 20965 | 2222 | 271 | 1089 |
| S7 search p50 (ms) | 454 | 505 | 312 | 1919 | 1870 | 308 | 1025 |

<sub>\* Supermemory's scope cells are confounded (§7). † Cognee's zero-setup mode
enforces no isolation (§7). ‡ DinoMem's S2 pass is conditional on the caller keying
the fact (`factKey`); plain writes get no temporal disambiguation, whereas Zep
invalidates automatically (§6, §11). S7 = bare-search mode; DinoMem's recommended
`rerank:true` mode adds ~3–4 s per search (§8).</sub>

**Per-scenario analysis.**

- **S1 (contradiction).** DinoMem is the only system with both a conflict-detection
  API and policy-based resolution (it blocked the executor's conflicting write under
  `planner_wins` with a high-severity conflict description). No other system exposes
  a conflict-surfacing API. Mem0's write-time LLM deduplication does not resolve the
  contradiction — we verified the stale and updated values coexist.
- **S2 (temporal).** Two systems answer point-in-time queries correctly, via
  opposite contracts. Zep extracts facts into a bitemporal graph and *automatically*
  invalidates the stale one (`invalid_at = T1`) with no caller involvement. DinoMem
  passes when both writes carry the same `factKey`: its bi-temporal versioning
  closes the prior fact's validity window on the second write, and `at_time` then
  isolates each fact (T0 → F1 only, T1 → F2 only; run `2026-07-05-164423`). Without
  a fact key — a plain write under the default `ignore` policy — both contradicting
  facts remain visible at every `at_time` point: DinoMem does not supersede on
  semantic contradiction alone. Same passing cell, different contract; callers who
  never key their facts get no temporal disambiguation, and we report the pass as
  conditional on that opt-in. All others lack temporal queries entirely.
- **S3/S5 (scope, isolation).** These are expressible as filter predicates, so the
  baselines pass — confirming they do not differentiate memory systems from vector
  stores. The informative split is intra-tier: **verbatim stores (pgvector, LangMem,
  DinoMem) preserve a re-scoped fact; dedup/aggregating stores (Mem0, Supermemory)
  silently drop the scope change.**
- **S4 (CRDT).** Measured live for DinoMem; N/A for every other shipping system.
  DinoMem ships an op-based LWW-Register CvRDT engine behind a black-box replica/sync
  API (`replica_write` / `sync` / `state`). In the live run (`2026-07-05-161701`),
  two replicas took four concurrent conflicting writes, gossiped out-of-order, and
  converged to one identical, lossless state; replaying delivery in 10 distinct
  orders produced exactly one distinct final state (*deterministic*), at ~1.5 s
  wall-clock per out-of-order sync round-trip. The engine's convergence is
  additionally **property-tested and empirically order-independent** in the core
  (order-independence across shuffles, the CvRDT laws — commutativity, associativity,
  idempotence — no-lost-writes vs an independent brute-force reference, and a
  CRDT-vs-naive-LWW ablation); a property-test suite, **not** a machine-checked
  proof. Every other system stays N/A for lack of a replica surface: their
  convergence is *unmeasured*, not failed. The live run's scale is deliberately
  small (2 replicas, 4 concurrent ops) — a correctness check, not a
  distributed-systems stress test (§10). The reference implementation also passes (§3.5).
- **S6 (policy).** DinoMem satisfies all four policies to spec; no other system
  ships conflict policies.
- **S7 (latency).** A ~70× spread: LangMem/Zep ≈ 300 ms; pgvector ≈ 500 ms;
  DinoMem/Mem0 ≈ 1.1 s; Supermemory ≈ 2.2 s; Cognee ≈ 21 s/write (per-write LLM
  graph extraction). DinoMem now has a full distribution (write 1085.6 ± 103.5 ms
  over N=300, p99 1432.6; search 1036.6 ± 115.1 ms over N=150, p99 1340.0) — in the
  bench's **bare hybrid-search mode**. Its recommended relevance mode (`rerank:true`)
  adds a further ~3–4 s per search (2.6–6.3 s per call measured at application
  level, §8); applications should budget for the operating mode they will run.

## 7. Operational Findings

Static metrics understate what running the systems revealed:

- **LLM-quota coupling (DinoMem).** Conflict detection/extraction is backed by a
  generative model (Gemini); under a daily free-tier quota it returns `5xx` rather
  than degrading gracefully. This reproduced across a month: the June S6 run
  completed only after provisioning fresh model quota, and in July the S1 scenario
  crashed on a quota 429 surfaced as `500` (run `2026-07-06-010838`) and passed only
  after rotating to a fresh key (run `2026-07-06-013045`). Both runs are committed —
  an honest demonstration of operational fragility in the authors' own system.
- **A documented filter that does not filter (DinoMem).** The live endpoint accepts
  a `factKeyPrefix` search parameter but performs no filtering with it (all org
  memories are returned regardless). Callers must isolate by `workflowId`, which
  filters exactly. A second defect in the authors' own system — found by the
  application-level run (§8), not by the grid.
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

## 8. Application-Level Validation

Grid scenarios are synthetic by design; to check that the measured properties
survive contact with a real application, we wired DinoMem into a production-shaped
multi-agent app — a three-persona financial-debate application in which
Miser/Visionary/Twin agents argue purchase decisions and persist verdicts — behind
the same pluggable backend seam as three other memory systems, and ran live debate
sweeps against the deployed service. Findings:

1. **Cross-session recall was faithful** in every debate round, with zero
   confabulation and zero cross-persona voice bleed.
2. **Bi-temporal supersession was observed end-to-end**: re-debating the same
   purchase wrote the same fact key, closed the prior fact's validity window
   (`valid_to` set, `superseded_by` pointing at the new write), exposed
   bidirectional lineage via the history API, and excluded the superseded fact
   from subsequent searches. Notably, supersession triggered on the fact key
   alone, with no conflict-policy involvement.
3. **Every search emitted an immutable audit receipt** attributing the read to the
   calling agent, with the returned memory identifiers recorded.
4. **The recommended `rerank:true` mode measured 2.6–6.3 s per search** versus
   ~1.0 s in the bench's bare mode, putting memory at ~15% of end-to-end debate
   wall-clock.
5. **The `factKeyPrefix` defect (§7) was discovered here, not by the grid** —
   evidence that application-level dogfooding catches what scenario grids miss.

Raw transcripts and assertion logs are committed alongside the harness.

## 9. Discussion

The results refute a one-dimensional reading of "memory system." Coordination
capabilities are **disjoint across vendors**: contradiction handling, policy, and
replica convergence are provided by one system (DinoMem); temporal validity by two,
under opposite contracts (Zep automatically, DinoMem only for caller-keyed facts);
and several "memory systems" provide nothing a vector store does not. Two
implications follow. First, **buyers should select by the specific coordination
property their multi-agent application requires**, verify the vendor even exposes
an API for it, then check **what the caller must do to activate it** — a capability
that requires an opt-in the application never performs is, for that application,
absent. Second, **a raw `pgvector` table is a strong, cheap baseline** at
modest scale and faithful-retrieval needs — the managed premium is justified only by
the coordination axes above.

## 10. Threats to Validity

- **Statistical.** Most correctness cells are single deterministic runs; S7 retains
  small N on two quota-limited hosted systems (Supermemory, Cognee). Absolute
  latencies are environment- and tier-bound.
- **Construct.** Several systems store no scope label, so scope is emulated in the
  adapter; S3/S5 therefore partly measure the adapter. We mark such cells. S2 grants
  each system its native temporal mechanism: Zep invalidates automatically, DinoMem
  requires the caller to key the fact — the cell is a pass under that disclosed
  contract, and applications that never set fact keys should read DinoMem's S2 as
  unavailable to them.
- **Coverage.** S4 is measured for exactly one system, and at deliberately small
  scale (2 replicas, 4 concurrent ops, 10 delivery orders): it establishes black-box
  convergence, not behavior under partition, scale, or adversarial interleavings.
  For all other systems CRDT convergence is *unmeasured*, not failed.
- **Free-tier artifacts.** Quotas, indexing lag, and search recall on free tiers may
  differ from paid deployments; we document the tier per system.
- **Versioning.** Hosted backends can change server-side behavior we cannot pin; we
  pin client/package versions, commit run manifests with git SHAs, and re-publish on
  a cadence, noting drift.

## 11. Conflict of Interest

The authors develop **DinoMem**, one of the seven systems under test — and in the
July 2026 runs reported here, DinoMem passes **every** correctness metric in the
grid. A benchmark whose authors' own system posts a perfect column deserves maximal
scrutiny, so we condition each headline cell explicitly rather than asking for
trust. **S2** is a pass *only under a disclosed contract*: the caller must key the
fact (`factKey`); plain writes get no temporal disambiguation, whereas Zep's pass
requires no caller opt-in — on out-of-box behavior, Zep's temporal contract is
strictly stronger than ours. **S1/S6** passed only after rotating LLM quota; the
committed run pair (`2026-07-06-010838` crash, `2026-07-06-013045` pass) documents
that under quota pressure our system crashes rather than degrades. **S4** is a
measured pass, but at smoke scale (2 replicas, 4 ops, 10 delivery orders), and
DinoMem is also the *only* system with a drivable replica surface — an asymmetry
that favors us by construction, since no competitor can even be measured there. The
engine's convergence claim rests on a property-test suite (order-independence
across shuffles, the CvRDT laws, no-lost-writes vs an independent brute-force
reference, a CRDT-vs-naive-LWW ablation), **not** a machine-checked proof; we claim
*property-tested*, never *proven* or *guaranteed*. We mitigate as follows: (i) this
statement is prominent; (ii) the June 2026 runs — in which the same product failed
S2's temporal assertions and crashed under quota — remain committed and published
alongside the July runs, never overwritten; (iii) we document two defects in our
own system found during this work (quota-coupled 5xx, a filter parameter that
performs no filtering; §7); (iv) every scenario is a public, deterministic script,
no metric is decided by an LLM judge, and every cell links to a committed raw trial
log, so any reader can reproduce or refute; (v) adapters and configuration
overrides are open to PRs from competing vendors, with maintainer merge rights
limited to harness code. We report no single aggregate score, and we encourage
readers to treat any all-green column — ours included — as a claim to reproduce,
not a conclusion to accept.

## 12. Conclusion & Future Work

dinomem-bench reframes memory evaluation from single-agent recall to multi-agent
coordination, and finds the capability landscape sharply differentiated:
contradiction handling, conflict policy, and measured replica convergence in one
system; automatic temporal invalidation in another; caller-keyed temporal
versioning validated end-to-end at application level; and a raw vector store
matching every managed system wherever coordination machinery is not required.
v0.2 will add: a rerank-inclusive S7 operating mode (bare-search latency
understates the recommended configuration by 3–6×); an audit-receipt scenario
(S8); larger-scale S4 (more replicas, more concurrent ops, adversarial
interleavings); per-operation cost instrumentation; confidence intervals from
seeded repeats; and an adversarial scenario (prompt injection via memory writes).
We invite the community to run the harness, contribute adapters, and challenge the
methodology.

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
