"""S4 — Concurrent writes (CRDT). DESIGN §4 S4. The headline differentiator.

Multiple replicas take CONCURRENT, conflicting writes (same key, different
values, disjoint vector clocks), then gossip in out-of-order / reversed delivery.
A CRDT-correct system must:
  - CONVERGE   — every replica reaches the SAME resolved state regardless of the
                 order syncs were delivered in,
  - be LOSSLESS — no write is silently dropped: every key that was written is
                 still present after merge (observable through the black-box
                 state API — a second, distinct key that must survive alongside
                 the contended one), and
  - be DETERMINISTIC — the same final state across many randomised sync orders,
                 with a single, reproducible winner for the contended key.

Systems without a drivable replica/vector-clock API are scored N/A (they raise
`Unsupported`). As of CRDT V3, DinoMem exposes that API (POST/GET
/v1/crdt/replicas/...) and its convergence engine is property-tested in the core
(agentmem/supabase/functions/api/lib/crdt-merge.test.ts: order-independence, the
CvRDT laws, no-lost-writes vs an independent brute force, partial-sync
convergence, and an LWW ablation). It is therefore the only system under test
that can run S4 end-to-end; the others remain N/A.
"""

from __future__ import annotations

import random
import time

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability
from .base import Scenario, MetricResult

WF = "s4-wf"


class S4Crdt(Scenario):
    id = "S4"
    slug = "s4_crdt"
    title = "Concurrent writes (CRDT)"
    requires = frozenset({Capability.VECTOR_CLOCK})

    def _seed_conflict(self, sut: SUTAdapter) -> None:
        # CONCURRENT conflicting writes on the SAME key (Owner): each replica is
        # unaware of the other, so their vector clocks are disjoint ({R1:1} vs
        # {R2:1}) — a genuine concurrent conflict the engine must resolve to ONE
        # deterministic winner.
        sut.replica_write("R1", "Owner is Alice.", agent_id="planner", workflow_id=WF, vclock={"R1": 1})
        sut.replica_write("R2", "Owner is Bob.", agent_id="executor", workflow_id=WF, vclock={"R2": 1})
        # Two MORE concurrent writes on DISTINCT keys, one per replica. These are
        # not contended, so a lossless merge MUST retain both — and because that
        # is visible through the plain state API (not just an internal history
        # hook), losslessness is checkable as a black box on any SUT with the
        # replica surface, DinoMem included.
        sut.replica_write("R1", "Budget is 100.", agent_id="planner", workflow_id=WF, vclock={"R1": 2})
        sut.replica_write("R2", "Region is EU.", agent_id="executor", workflow_id=WF, vclock={"R2": 2})

    @staticmethod
    def _state(sut: SUTAdapter, replica: str) -> list[str]:
        """Resolved contents on one replica, order-normalised so the comparison
        is over the SET of (key->winner) values, not list order."""
        return sorted(h.content for h in sut.replica_state(replica, workflow_id=WF))

    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        out: list[MetricResult] = []
        if not sut.supports(Capability.VECTOR_CLOCK):
            for m in ("S4.converge", "S4.deterministic", "S4.lossless"):
                out.append(self.na(m, "no vector-clock/replica API"))
            return out

        try:
            # --- converge + lossless: sync in REVERSED order on each replica ----
            sut.setup()
            self._seed_conflict(sut)
            t0 = time.perf_counter()
            sut.replica_sync([("R1", "R2"), ("R2", "R1")])  # out-of-order delivery
            sync_ms = (time.perf_counter() - t0) * 1000
            s1 = self._state(sut, "R1")
            s2 = self._state(sut, "R2")
            out.append(self.check("S4.converge", s1 == s2, detail=f"R1={s1} R2={s2}"))

            # Lossless = both the contended key AND each replica's distinct key
            # survive the merge. After convergence every replica holds exactly
            # three keys: owner (one winner), budget, region. We assert the two
            # uncontended writes were NOT dropped, observable purely via state.
            merged = set(s1)
            has_budget = any("budget" in c.lower() for c in merged)
            has_region = any("region" in c.lower() for c in merged)
            owner_winners = {c for c in merged if "owner" in c.lower()}
            # Belt-and-suspenders: if the SUT also exposes a raw op history hook,
            # confirm every issued op is durably retained (>= 4 ops) — but the
            # primary, API-observable signal is the surviving distinct keys above.
            history = sut.replica_history(workflow_id=WF) if hasattr(sut, "replica_history") else None
            history_ok = True if history is None else len(history) >= 4
            lossless = has_budget and has_region and len(owner_winners) == 1 and history_ok
            hist_detail = "n/a" if history is None else f"{len(history)} op(s) in history"
            out.append(self.check(
                "S4.lossless", lossless,
                detail=f"budget={has_budget} region={has_region} owner_winners={len(owner_winners)} ({hist_detail})",
            ))

            # --- deterministic: same final state across randomised sync orders --
            rng = random.Random(42)
            finals = set()
            orders = [
                [("R1", "R2"), ("R2", "R1")],
                [("R2", "R1"), ("R1", "R2")],
            ]
            for _ in range(8):
                o = orders[0][:] + orders[1][:]
                rng.shuffle(o)
                orders.append(o)
            for order in orders:
                sut.setup()
                self._seed_conflict(sut)
                sut.replica_sync(order)
                fa = tuple(self._state(sut, "R1"))
                fb = tuple(self._state(sut, "R2"))
                finals.add((fa, fb))
            out.append(self.check(
                "S4.deterministic", len(finals) == 1,
                detail=f"{len(finals)} distinct final state(s) across {len(orders)} orders",
            ))

            # --- info: convergence cost under concurrent load (no pass/fail) ----
            # One reversed-order sync round-trip over 4 concurrent ops on 2
            # replicas. Operational colour only; not a correctness gate.
            out.append(self.info(
                "S4.converge_ms", round(sync_ms, 3),
                detail="wall-clock for one out-of-order sync round-trip over 4 concurrent ops / 2 replicas",
            ))
        except Unsupported as e:
            for m in ("S4.converge", "S4.deterministic", "S4.lossless"):
                out.append(self.na(m, str(e)))
        return out
