# AgentMem adapter — built; live run deferred

**Date:** 2026-06-12
**Adapter:** `agentmem_bench/suts/agentmem.py` (httpx against the v1 HTTP API).
**Status:** Built + wired (imports, registers, capabilities verified). **Live run
deferred** — the hosted AgentMem Supabase project (`lwbwcuuzoituanwhekyo.supabase.co`)
doesn't resolve (paused free-tier, same as the Fincil project). Needs the project
restored + `AGENTMEM_API_KEY` to run.

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
- **S4 = N/A:** no replica/sync API. Even AgentMem — the supposed S4 winner — can't
  be driven through the replica protocol via its public API. *Actionable for
  AgentMem: expose a replica/vector-clock test hook so S4 can actually score it;
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

## To run (once the project is restored)
```bash
AGENTMEM_API_KEY=... .venv/bin/python -m agentmem_bench --sut agentmem --scenarios all
# optional: AGENTMEM_BASE_URL to point at a self-hosted/local instance
```
