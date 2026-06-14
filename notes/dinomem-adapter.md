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
| ~~VECTOR_CLOCK~~ | **NOT exposed** — clocks tick internally + appear on reads, but there's no replica write/sync API |

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
- **S4 = N/A:** no replica/sync API. Even DinoMem — the supposed S4 winner — can't
  be driven through the replica protocol via its public API. *Actionable for
  DinoMem: expose a replica/vector-clock test hook so S4 can actually score it;
  otherwise the CRDT claim is untestable by black-box benchmarks.*
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
| S4 | converge / deterministic / lossless | — N/A ×3 (no replica API) | both N/A |
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
2. **S4 untestable black-box.** No replica/sync API → N/A even for DinoMem.
   *Actionable: expose a replica/vector-clock test hook.*
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
