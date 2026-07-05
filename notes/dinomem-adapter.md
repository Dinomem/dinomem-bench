# DinoMem adapter — built; live run deferred

**Date:** 2026-06-12
**Adapter:** `dinomem_bench/suts/dinomem.py` (httpx against the v1 HTTP API).
**Status:** Built + wired (imports, registers, capabilities verified). **Live run
deferred** — the hosted DinoMem Supabase project (`lwbwcuuzoituanwhekyo.supabase.co`)
doesn't resolve (paused free-tier, same as the Fincil project). Needs the project
restored + `DINOMEM_API_KEY` to run.

## API → SUTAdapter mapping (from the backend source `Mem/.../api`)

| Capability | Endpoint / behaviour |
|---|---|
| SCOPES | `scope` on write/search (private/team/global); search enforces visibility by `agentId` |
| CONFLICTS | `POST /v1/memory/conflicts` → `detectConflicts` (LLM, severity high/medium/low) |
| POLICIES | `PUT /v1/policies` — `ignore` / `planner_wins` / `timestamp_wins` / `human_in_loop` |
| TEMPORAL | `search` `atTime` |
| VECTOR_CLOCK | **Exposed as of CRDT V3** — `POST /v1/crdt/replicas/{rid}/write` `{key,value,agentId}` → op; `POST .../sync` `{from}` → `{synced}`; `GET .../state` → `[{key,value,opId,agentId}]`. Backed by a property-tested op-based LWW-Register CvRDT engine (`agentmem/.../lib/crdt-merge.ts`, tested in `crdt-merge.test.ts`). The adapter maps `replica_write`/`replica_sync`/`replica_state` straight onto these. |

**Key behavioural finding — policies enforce at WRITE time** (`lib/resolution.ts`):
- `planner_wins` → **blocks** an `executor` write that high-conflicts (planner memory stays)
- `timestamp_wins` → write proceeds and **soft-deletes** (supersedes) the old conflicting memory
- `human_in_loop` → **blocks** the write + dispatches a `memory.conflict_detected` webhook
- only **high-severity** conflicts trigger any of this

This drove two harness fairness fixes (committed): S1/S6 now **set the policy
before** the conflicting writes (a write-time enforcer no-ops if policy is set
after), and `P.human_in_loop.correct` accepts *surfaced OR keep-both* (the read
outcome is implementation-specific; the unambiguous signal is surfacing).

## Adapter specifics
- **Run isolation:** every `workflow_id` is namespaced `ambench-<rand>:<wf>` so
  repeated runs against the shared hosted org don't collide (no bulk-delete API).
- **Blocked-write capture:** a write blocked by policy returns the conflict body
  instead of raising; the adapter records it and `pending_events()` surfaces the
  `human_in_loop` ones (the client-observable HITL signal — webhook delivery
  itself isn't observable client-side).
- **S4 = drivable (CRDT V3).** DinoMem now ships the replica/sync API the
  convergence test needs, so S4 runs end-to-end against it — concurrent conflicting
  writes on the same key (+ distinct uncontended keys per replica) → out-of-order
  gossip → assert all replicas converge to one deterministic, lossless state. The
  adapter namespaces the replica id (`<ns>.<replica>`) and the register key
  (`<ns>:<wf>:<key>`) per run for isolation on the shared org. **DinoMem is the only
  SUT with this surface**; the others stay N/A. The convergence guarantee itself is
  the core's CvRDT property suite (`crdt-merge.test.ts`), not a black-box-derived
  claim. (Historical: earlier the adapter advertised NOT VECTOR_CLOCK and flagged
  "expose a replica/vector-clock test hook" as actionable — CRDT V3 did exactly
  that.) The committed `results/COMPARISON.md` S4-DinoMem cell flips to ✅ only after
  a live run against a deployed CRDT-V3 instance is recorded in `runs/`.
- **S7 cost = 0 (caveat):** extraction (Gemini) + embeddings are server-side and
  not billed back to the client per-op, so `$/1k` isn't client-observable. Latency
  IS measured (real hosted round-trips).

## What the live run will actually resolve (genuine open questions)
1. **Severity gating** — does `detectConflicts` rate "Deadline is Friday" vs
   "…Monday" as **high**? If not, the policies never fire and S1.resolved / S6 fail.
   This is the single biggest unknown.
2. **Temporal under `ignore`** — S2 writes F1 then contradicting F2 with no policy
   set. Does `atTime=T1` return F2 only (auto-supersede) or both? Determines T1.t1.
3. **Scope + isolation** (S3/S5) — expected to pass like pgvector, but verifies the
   service actually enforces private visibility + workflow isolation.

Predicted (UNVERIFIED until the service is up): S1 detected/resolved ✅, consistent
✅; S2 bitemporal ℹ️Y, t0/t1 ⟶ TBD; S3 ✅×3; S4 N/A×3; S5 ✅; S6 ✅×5 (severity-
dependent); S7 latency real / cost 0. The point of running is to confirm or break
these — especially (1).

## First-run results (2026-06-12, project restored)

| Scenario | Metric | dinomem | vs pgvector |
|---|---|---|---|
| S1 | C1.detected | ✅ Y | pgvector N/A — **DinoMem fills it** |
| S1 | C1.resolved | ✅ Y (planner_wins blocked the executor) | pgvector N/A — **DinoMem fills it** |
| S1 | C1.consistent | ✅ Y | both ✅ |
| S2 | T1.bitemporal | ℹ️ Y (atTime accepted) | pgvector ℹ️ N |
| S2 | T1.t0 / t1 | ❌ N / ❌ N — see finding | pgvector N/A |
| S3 | isolated / team_visible / cross_workflow | ✅ Y ×3 | both ✅ — not differentiating |
| S4 | converge / deterministic / lossless | — N/A ×3 *(this 2026-06-12 run predates CRDT V3; the replica API did not yet exist)* | both N/A |
| S6 | P.*.correct | ⛔ blocked (Gemini quota) | pgvector N/A |
| S7 | latency / cost | not run (quota + 1000-write cost) | pgvector ran |

**The headline:** DinoMem **fills S1** (conflict detection + `planner_wins`
resolution) where the pgvector floor is N/A — the real, measured differentiation a
raw vector store can't provide. S3 (scope) is passed by both, so it doesn't
separate them; S4 is N/A for both (no replica API).

### Findings the run surfaced
1. **S2 temporal gap.** `atTime` is accepted (bitemporal=Y) but `at_time=T0` and
   `=T1` both returned *both* contradicting facts. Under the default `ignore`
   policy DinoMem doesn't supersede, so both stay valid and `atTime` doesn't
   disambiguate "what was true at T". *Caveat:* my adapter uses client-side write
   timestamps (the `/write` response returns only `writeId`, no `created_at`), so
   the T0/T1 points are approximate — a clean S2 needs server timestamps + a
   `timestamp_wins` variant. Recorded as a real gap pending that follow-up.
2. **S4 untestable black-box (at the time).** No replica/sync API → N/A even for
   DinoMem on this run. *Actionable: expose a replica/vector-clock test hook.* —
   **RESOLVED in CRDT V3 (2026-06-14):** the core now ships
   `POST/GET /v1/crdt/replicas/{rid}/{write,sync,state}` over a property-tested
   CvRDT engine, the adapter advertises `VECTOR_CLOCK` and drives it, and S4 runs
   end-to-end against DinoMem (the only SUT that can). The matrix cell flips to ✅
   on the next live run recorded in `runs/`.
3. **Operational fragility (the big one).** Conflict detection + extraction call
   **Gemini 2.5 Flash server-side**, and under quota they return **5xx, not graceful
   degradation**: `/conflicts` → `502 "[GoogleGenerativeAI] 429 You exceeded your
   current quota"`; policy `write` → `500 "Internal server error"`. The first S1 run
   passed; reruns + S6 failed once the free-tier Gemini quota was burned (every
   write also fires a background extraction). *Actionable: graceful degradation /
   queue / fallback when the extraction LLM is rate-limited; and S7's 1,000-write
   workload needs real Gemini quota.* This is why S6/S5/S7 are deferred to a quota
   reset.

### Harness fixes from this run (committed)
- `atTime` must be `Z`-suffixed (Zod `.datetime()` rejects `+00:00`).
- Adapter raises with the response body, so a crash detail is debuggable
  (that's how the Gemini-429 root cause was found, not an opaque MDN link).
- `Scenario.settle()` waits for the first write to be index-visible before the
  conflicting one (reliable conflict detection; no truly-simultaneous writes —
  that's S4's job).

## To run (once the project is restored)
```bash
DINOMEM_API_KEY=... .venv/bin/python -m dinomem_bench --sut dinomem --scenarios all
# optional: DINOMEM_BASE_URL to point at a self-hosted/local instance
```

---

## Fincil dogfood findings (2026-07-05) — live deploy confirmed

The DinoMem hosted instance is **fully live** as of 2026-07-05 (no longer paused).
`GET .../api/health → {"ok":true}`. The existing `AGENTMEM_API_KEY` (`sk-0a3f…`)
is a valid DinoMem org key on the live endpoint (back-compat env name still works).

DinoMem was wired into the **Fincil** benchmark (the 3-persona debate app:
Miser/Visionary/Twin; TypeScript + Vercel AI SDK) as `MEMORY_PROVIDER=dinomem`,
with plain `fetch` against the REST API. Full notes:
`/mnt/308E51BA8E517974/fincil-remastered/notes/dinomem-test/`.

### API response shapes confirmed on live endpoint

**`POST /v1/memory/write`** returns:
```json
{ "writeId": "uuid", "conflictsChecked": true, "embeddingPending": false }
```
- `conflictsChecked: true` = API ran conflict detection (auto-resolved by policy)
- Does NOT echo back the factKey — the adapter must hold it locally
- The adapter's `data.get("writeId", "")` mapping is correct ✅

**`POST /v1/memory/search`** returns a **flat array** (not `{results:[...]}` wrapper):
```json
[{"id":"...","content":"...","agent_id":"...","scope":"team","workflow_id":"...","score":0.016,...}]
```
- The adapter's `if isinstance(rows, dict): rows = rows.get("results", ...)` fallback
  handles both cases correctly ✅
- `relevance_score` appears only when `rerank:true` is passed:
  - near-exact match: 1.0
  - related match: 0.4
  - unrelated: 0.0 (collapses to raw score ~0.016)
- Without `rerank`, the raw `score` ~0.016 is too compressed to use as a filter

### Per-field workflowId isolation — confirmed

`workflowId` passed in the search body is an **exact equality filter** — only
memories with that exact `workflow_id` value are returned. This is the correct
per-user isolation mechanism. The adapter's `_wf()` namespacing (`ambench-<ns>:<wf>`)
is exactly right.

**`factKeyPrefix` is NOT filtering on the live endpoint.** Passing
`factKeyPrefix: "prefix."` in the search body returns ALL memories in the org
(including those with different factKey prefixes AND those with no factKey).
Do not rely on factKeyPrefix for isolation — workflowId is the only reliable filter.

### Rerank latency (new S7 data point)

The bench runner does NOT pass `rerank: true` to the DinoMem search endpoint.
The Fincil integration does (for relevance filtering). Measured overhead:

| Recall scenario | Without rerank (bench) | With rerank:true (Fincil) |
|---|---|---|
| S7 search p50 (bench) | **891ms** | — |
| D1 cold-start (Fincil) | — | **2,586ms** |
| D2 recall-related | — | **6,294ms** |
| D3 unrelated | — | **3,596ms** |

Rerank adds ~3-4s per search call. The S7 p50=891ms numbers in `results/COMPARISON.md`
reflect **bare hybrid search** (rerank OFF) — that's what the bench adapter measures.
Real applications using rerank for relevance filtering should expect 2.5-6s per search.

**Implication for S7:** the 891ms figure is not wrong, but it measures a different
operating mode from the recommended production setting. S7 should optionally report
rerank-ON latency in a future run.

### Rerank silent-degradation confirmed mitigated

The Fincil integration detects if rerank appears unavailable (i.e., `relevance_score`
equals raw `score` across all hits, ~0.016) and logs a warning without injecting
anything — safe-by-construction. This matches the behaviour identified in the
agentmem Block I/M testing and is NOT a new failure mode; it's the same mitigation.

### P0 conflicts via regular write path

3-way concurrent write of the same `factKey` from different `agentId`s (via
`Promise.all`) → all three writes succeed with `conflictsChecked: true` but
`GET /v1/crdt/conflicts` returns **0 open conflicts**. The default org policy
auto-resolves (likely `timestamp_wins`). The S1/S6 bench scenarios that exercise
conflicts DO work because they: (1) set `human_in_loop` policy first, and (2) use
the `detectConflicts` LLM-severity path (not just concurrent writes). This is
consistent — the regular write path is not the same as the CRDT replica path.

### P1 bi-temporal (factKey supersession) — confirmed structural

Writing with `factKey: "fincil.purchase.<slug>"` and `workflowId: userId` — when
the same factKey is written twice (same purchase query slug), the second write closes
the prior validity window and opens a new one. `GET /v1/memory/:id/history` returns
the supersession lineage. In the Fincil test, 3 different slugs were used so no
supersession occurred this run (by design), but the mechanism is confirmed.

### P2 receipts — confirmed per-search

Every `POST /v1/memory/search` generates an immutable receipt in
`GET /v1/receipts`. In the Fincil 3-debate run: 8 receipts total, each with
`reader_agent = agentId` passed in the search body, and `returned_ids` = the
memory row IDs surfaced. This is new behaviour vs the bench runs (the bench adapter
does NOT read receipts; this is a gap worth filling in S7 or a new S8).

### S2 temporal gap — still open, but narrowed

The original S2 failure ("atTime returns both facts under ignore policy") is still
reproduced conceptually — the Fincil integration doesn't exercise atTime directly.
However, the factKey supersession mechanism confirms that DinoMem CAN invalidate
a prior fact window when a newer write to the same factKey arrives. The S2 failure
is specifically about `atTime` returning the correct *single* fact at each point —
this requires the search to filter by `valid_to` correctly. Still marked as a real
gap pending a `timestamp_wins` policy repro.

### Summary for the next bench run

| Finding | Status for next run |
|---|---|
| Live endpoint | ✅ up — can run S1–S7 now |
| S4 (CRDT V3) | ✅ ready — replica API deployed; first live run needed |
| S7 rerank-ON latency | 🆕 add as a separate row (currently only bare search measured) |
| factKeyPrefix | ⚠️ don't use for scenario isolation — workflowId only |
| P2 receipts | 🆕 consider a new receipt-assertion in S7 or a new S8 |
| Gemini quota | ⚠️ still the constraint — S1/S6 detection burns quota; plan for it |

---

## Live bench run (2026-07-05) — S4 ✅ + S2 partial + S1/S6 quota-blocked

**Run order:** S4 → S2 → S1 → S7 (parallel). S6 skipped — quota gone by S1.

### Adapter fix required: `evidenceId` on CRDT writes

The live endpoint now enforces provenance on every CRDT op (FR-P0-3):
`POST /v1/crdt/replicas/{rid}/write` requires `evidenceId: uuid` referencing an
existing `memory_events` row in the org. Missing it → `400 "evidenceId: Invalid
input: expected string, received undefined"`. **Fix applied to the adapter**
(`dinomem_bench/suts/dinomem.py`): `replica_write()` now creates a backing
`POST /v1/memory/write` first and uses the returned `writeId` as `evidenceId`.
This adds one extra write per CRDT op but satisfies the API contract exactly.

### S4 — ✅ ALL 3 PASS (first live run, run `2026-07-05-161701`)

| Metric | Result | Detail |
|---|---|---|
| S4.converge | ✅ Y | R1 == R2: `['Budget is 100.', 'Owner is bob.', 'Region is eu.']` |
| S4.lossless | ✅ Y | budget=True, region=True, owner_winners=1 |
| S4.deterministic | ✅ Y | 1 distinct final state across 10 random sync orders |
| S4.converge_ms | ℹ️ 1496ms | wall-clock for one out-of-order sync round-trip over 4 concurrent ops |

**Bob won the contended `Owner` key** (concurrent Alice/Bob writes with disjoint
vclocks; LWW-Register converged deterministically). Both uncontended keys (`Budget`
100, `Region` eu) survived — lossless. All 10 randomised gossip orders reached
the same state — deterministic.

**These are the first live measured S4 results for any system under test.**
The COMPARISON.md S4-DinoMem cells flip from N/A to ✅ after this run is
ingested by compare.py.

### S2 — T1.t0 ✅ (improvement), T1.t1 ❌ (still failing) — run `2026-07-05-161904`

| Metric | June run | This run | Detail |
|---|---|---|---|
| T1.bitemporal | ℹ️ Y | ℹ️ Y | — |
| T1.t0 | ❌ N | ✅ Y | at_time=T0 → `['project status is green.']` only |
| T1.t1 | ❌ N | ❌ N | at_time=T1 → `['project status is green.', 'project status is red.']` |

**T0 improvement**: `atTime=T0` now correctly returns only "green". The `settle()`
mechanism is more reliable here — T0 (the timestamp at first write) falls before
the second write lands, so atTime correctly excludes the later "red" fact.

**T1 still fails**: at T1, both facts are returned. Under the default `ignore`
policy, DinoMem does not supersede the old fact, so both stay valid and atTime
can't distinguish "what was true at T1" from "what was true at T0".

#### timestamp_wins variant (standalone test, not a formal run)

Set `timestamp_wins` policy → write F1 (green) → write F2 (red) → query atTime:
- `atTime=T0` → `[]` empty — client-side T0 fires BEFORE the server commits the write;
  the server-assigned `created_at` is later than our T0
- `atTime=T1` → both green and red — `conflictsChecked: false` on the F2 write
  (the two facts weren't flagged as conflicting by the LLM), so `timestamp_wins`
  never fired; no supersession occurred

**Root cause confirmed**: The S2 gap has two layers:
1. **Client-side timestamps** — the write response returns `{writeId,conflictsChecked,embeddingPending}` but NO `created_at`. The adapter falls back to `datetime.now()` which is before the server's `created_at`. atTime queries must use server timestamps.
2. **timestamp_wins only supersedes when LLM conflict detection fires** — two semantically-different facts ("green"/"red") may not trigger Gemini's conflict detection. Supersession requires an explicit conflict classification.

**What would actually close S2:** API returns `created_at` in write response (so
S2 can use server-assigned T0/T1), AND the test facts are crafted to trigger LLM
conflict classification under `timestamp_wins`. Still marked as a real open gap.

### S1 — ⛔ BLOCKED (Gemini quota, run `2026-07-05-162040`)

`POST /v1/memory/conflicts` → `502` with body `"[GoogleGenerativeAI Error]: 429 Too Many Requests — You exceeded your current quota"`. The first conflict detection call exhausted the org's free-tier Gemini quota (S2's two writes + background extraction already consumed it). S1/S6 deferred to next quota cycle.

### S7 — running (in background, 150 writes / 75 searches)

Running while S1 was attempted. Results pending — will be captured in `runs/` once complete.

### Summary of this run

| Scenario | Metric | Status | Note |
|---|---|---|---|
| S4 | converge / deterministic / lossless | ✅ ×3 | **First live CRDT run — all pass** |
| S4 | converge_ms | ℹ️ 1496ms | new latency data point |
| S2 | T1.bitemporal | ℹ️ Y | unchanged |
| S2 | T1.t0 | ✅ Y | **improved from June ❌** |
| S2 | T1.t1 | ❌ N | still failing (ignore policy, both facts) |
| S1 | all | ⛔ | Gemini 429 quota exhausted |
| S6 | all | ⛔ | skipped (quota gone) |
| S7 | latency | pending | 150w/75s run in background |

### Adapter changes committed this session

- `replica_write()` now creates a backing `/v1/memory/write` first and passes its `writeId` as `evidenceId` (provenance enforcement, FR-P0-3).
- Module docstring updated to document the `evidenceId` requirement.
