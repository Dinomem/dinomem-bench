# We benchmarked 7 memory systems on the things that actually break multi-agent apps

*Draft — agentmem-bench v0.1 results. 2026-06-13.*

**TL;DR.** Every published agent-memory benchmark measures one agent recalling
facts from one long conversation. But production multi-agent systems don't fail on
recall — they fail on *coordination*: two agents writing contradictory facts,
"what was true last Tuesday?", scope leaks across workflows, divergent state under
concurrent writes. So we built [`agentmem-bench`](https://github.com/rooney011/agentmem-bench):
seven scenarios (S1–S7) that stress exactly those, run against seven shipped memory
systems on the same hardware and LLM. The headline: **different systems fill
different gaps, and "best memory system" is a category error.** Only AgentMem
handled contradiction + policy; only Zep handled temporal validity; *no* system
could be tested on CRDT convergence (none exposes the API); and a raw `pgvector`
table quietly matches the managed systems on everything they *don't* differentiate
on.

> **Conflict-of-interest disclosure, up front.** We build AgentMem. We also wrote
> and ran this benchmark. So treat AgentMem's wins with appropriate skepticism —
> and note that we're publishing, in the same table, the scenarios where AgentMem
> has a **gap** (S2), where it's **untestable** (S4), and the **operational
> fragility** that nearly stopped us from finishing (its conflict detection ran out
> of a free-tier Gemini quota mid-run). Every scenario is a deterministic script in
> the repo; every number links to a trial JSONL. Reproduce it and tell us where
> we're wrong.

---

## Why another benchmark

LoCoMo and LongMemEval measure single-agent long-term recall. Useful — but Letta
has [argued](https://www.letta.com/blog/long-conversation-locomo) those measure
retrieval, not agent memory. And nothing public stresses **multi-agent** memory.
The Cemri et al. study of 1,600+ multi-agent traces (arXiv:2503.13657) makes
**inter-agent misalignment** — agents ignoring, duplicating, or contradicting each
other's work — one of its three top-level failure categories, with 41–86.7% failure
rates; a follow-on finds **~79% of failures** come from coordination/specification
issues, not model capability (arXiv:2604.16339). Memory is the substrate where that
gets solved or compounded.

So we asked a sharper question: **does a managed "memory system" actually beat a
raw vector store for multi-agent work — and on which dimension?**

## The scenarios

Each is a deterministic setup → operations → assertions script.

| | What it tests |
|---|---|
| **S1** Contradictory writes | two agents write conflicting facts → is the conflict surfaced + resolved per policy? |
| **S2** Temporal validity | write F1, then contradicting F2 → "what was true at T0 vs T1?" |
| **S3** Scope enforcement | private / team visibility; can agent B see agent A's private memory? |
| **S4** CRDT convergence | concurrent writes on two replicas, synced out-of-order → do they converge? |
| **S5** Cross-workflow isolation | does a workflow-A reader ever surface workflow-B content? |
| **S6** Policy fidelity | `ignore` / `timestamp_wins` / `planner_wins` / `human_in_loop` — does retrieval match each? |
| **S7** Operational | write/search latency percentiles + cost |

Systems under test: **AgentMem, Mem0, Zep, Cognee, Supermemory, LangMem, and a raw
pgvector baseline** — plus an in-process reference implementation (`FakeSUT`) that
passes everything, to prove the scenarios + assertions are sound. A system that
can't perform an operation scores **N/A**, not a failure (e.g. no `at_time` API →
N/A on S2). The pgvector floor is the control: *if a scenario can be passed by a
raw vector store, it isn't measuring memory-system value.*

## The results

| Scenario | pgvector | mem0 | zep | cognee | supermemory | langmem | **AgentMem** |
|---|---|---|---|---|---|---|---|
| **S1** conflict detect | N/A | N/A | N/A | N/A | N/A | N/A | **✅** |
| **S1** conflict resolve | N/A | N/A | N/A | N/A | N/A | N/A | **✅** |
| **S2** temporal (t0/t1) | N/A | N/A | **✅** | N/A | N/A | N/A | ❌ *gap* |
| **S3** scope isolated | ✅ | ✅ | N/A | N/A | ✅* | ✅ | ✅ |
| **S3** team-visible | ✅ | ❌ | N/A | N/A | ❌* | ✅ | ✅ |
| **S4** CRDT converge | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| **S5** isolation leak | 0% | 0% | N/A | N/A† | 0%* | 0% | 0% |
| **S6** policy fidelity | N/A | N/A | N/A | N/A | N/A | N/A | **✅ (all 4)** |
| **S7** write p50 | 307ms | 1143ms | 305ms | 20965ms | 2222ms | 303ms | 1005ms |
| **S7** search p50 | 309ms | 507ms | 302ms | 1919ms | 1870ms | 304ms | 892ms |

<sub>\* Supermemory's scope results are confounded — its free-tier search wouldn't
reliably retrieve our short test memories (see below). † Cognee's zero-setup mode
doesn't enforce isolation at all.</sub>

## What the table actually says

**S1 — contradiction: only AgentMem.** Two agents write "Deadline is Friday" and
"Deadline is Monday." Only AgentMem exposes a conflict-detection API *and* resolves
per policy (it blocked the executor's write under `planner_wins`, with a
high-severity conflict description). Every other system — including the graph ones
— has no API to surface a contradiction. **Mem0's much-advertised LLM dedup does
not resolve it**: we verified the stale and the new value silently coexist.

**S2 — temporal: only Zep.** Write a fact at T0, contradict it at T1, then ask what
was true at each time. Zep extracts facts as graph edges with bitemporal validity
and **auto-invalidates** the old one (`invalid_at = T1`), so `at_time=T0` returns
"green" and `at_time=T1` returns "red". It's the only system that gets this right.
AgentMem *accepts* an `at_time` parameter but returns both facts — a real gap we're
not hiding. Everyone else: no temporal API at all.

**S3 / S5 — scope: nobody's differentiator, but it splits the floors.** Scope and
workflow isolation are `WHERE`-clause-shaped, so the floors handle them — which is
the point: these scenarios don't separate a memory system from a vector store. The
interesting split is *within* the floor tier: **verbatim stores (pgvector, langmem,
AgentMem) pass "team-visible"; dedup/aggregating stores (Mem0, Supermemory) fail
it** — re-writing a fact at a wider scope is silently swallowed by content dedup.

**S4 — CRDT: everybody fails, for the same reason.** This was meant to be the
headline. It isn't — because **no system, including AgentMem, exposes a replica /
vector-clock API** you can drive to test out-of-order convergence as a black box.
AgentMem ticks vector clocks internally, but you can't reach them through the public
API. So S4 is N/A across the board (only the in-process reference passes). Honest
takeaway: *the convergence claim every CRDT-flavored memory system makes is
currently unverifiable from the outside.* That's a gap in the **products**, and a
to-do for v0.2 of the benchmark.

**S6 — policy fidelity: only AgentMem.** All four policies behaved to spec:
`ignore` keeps both, `timestamp_wins` supersedes to the latest, `planner_wins`
blocks the executor, `human_in_loop` blocks and emits an event. No other system
ships conflict policies.

**S7 — latency spans 70×.** langmem / zep / pgvector cluster at ~300 ms; AgentMem
and Mem0 around 1 s; Supermemory ~2.2 s; **Cognee ~21 s per write** (it runs LLM
graph extraction on every write). For many apps, that spread matters more than any
correctness checkbox.

## The operational findings (what running it actually taught us)

The scenario grid is half the story. The other half is what broke:

- **AgentMem (us): conflict detection is bound to the extraction LLM's quota, and
  it 5xx's instead of degrading.** Our backend's free-tier Gemini key hit its daily
  request cap mid-benchmark; conflict-detection writes returned `500` rather than
  failing gracefully. We also caught a `500` under near-simultaneous policy writes.
  Both are now on our fix list. (We only completed S6 after swapping in a fresh
  Gemini key on the backend — an honest illustration of the fragility.)
- **Mem0 & Supermemory dedup/aggregate identical content** and lose the scope
  change in the process (the S3 "team-visible" failure).
- **Supermemory's free-tier indexing is ~50 s/doc**, and its memory search
  returned nothing for our short factual writes — so its scope passes are largely
  "passing on empty results." We flag them as confounded rather than claim them.
- **Cognee, in its zero-setup mode, doesn't isolate at all** — with access control
  off, search queries the global graph and leaked 100% across workflows. Real
  isolation requires its multi-tenant layer. And it's the slowest by 10×.
- **Zep's extraction is async (~50 s)** but correct — the only system to actually
  deliver temporal validity.

## What this does *not* show

- **Single runs / small N** on most cells, and **free-tier accounts** with their
  own quirks (quotas, indexing lag). Absolute latencies are environment-bound.
- **S4 is untestable as a black box** for every hosted system — including ours.
- **Scope is emulated client-side** for several systems (they store no scope label),
  so S3/S5 partly measure our adapter, not just the system.
- We **don't** report a single "winner" score. We won't.

## So, which memory system?

Wrong question. The benchmark's clearest result is that the category is *not*
one-dimensional:

- Need **contradiction handling or resolution policies**? Only **AgentMem** did it.
- Need **"what was true at T?"**? Only **Zep** did it.
- Need **fast, cheap, faithful retrieval at modest scale**? A **raw pgvector
  table** (or LangMem) is hard to beat — and a lot of "memory systems" don't beat it.
- Need **CRDT convergence guarantees**? **No shipping product** lets you verify them
  today.

If you take one thing from this: stop asking for the best memory system, and start
asking which coordination property your multi-agent app actually needs — then check
whether your candidate even has an *API* for it.

## Reproduce it

```bash
git clone https://github.com/rooney011/agentmem-bench
python -m agentmem_bench --sut pgvector --scenarios all   # one SUT
python -m agentmem_bench.compare                          # the matrix
```

Every scenario is a deterministic script; every run writes a self-contained
`runs/<id>/` with per-metric JSONL + provenance. The full matrix is committed at
`results/COMPARISON.md`; per-system writeups (including the caveats above) are in
`notes/`. Adapters are ~100 lines each — **PR your own system, or fix ours.**

---

*Built by [devsforfun](https://github.com/rooney011). Methodology RFC + scenario
definitions in [`DESIGN.md`](../DESIGN.md). v0.2 will add a replica/vector-clock
test hook (so S4 can finally score someone) and tighter cost instrumentation.*
