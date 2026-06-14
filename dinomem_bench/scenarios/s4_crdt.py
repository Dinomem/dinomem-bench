"""S4 — Concurrent writes (CRDT). DESIGN §4 S4. The headline differentiator.

Two replicas take conflicting writes with different vector clocks, then sync in
reversed/randomised orders. A CRDT-correct system converges to the same final
state regardless of delivery order, and retains both writes in history.
Systems without a vector-clock API are scored N/A (DESIGN open question #2).
"""

from __future__ import annotations

import random

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
        # Concurrent writes (each replica unaware of the other -> disjoint vclocks).
        sut.replica_write("R1", "Owner is Alice.", agent_id="planner", workflow_id=WF, vclock={"R1": 1})
        sut.replica_write("R2", "Owner is Bob.", agent_id="executor", workflow_id=WF, vclock={"R2": 1})

    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        out: list[MetricResult] = []
        if not sut.supports(Capability.VECTOR_CLOCK):
            for m in ("S4.converge", "S4.deterministic", "S4.lossless"):
                out.append(self.na(m, "no vector-clock/replica API"))
            return out

        try:
            # --- converge + lossless: sync in REVERSED order on each replica ---
            sut.setup()
            self._seed_conflict(sut)
            sut.replica_sync([("R1", "R2"), ("R2", "R1")])  # reversed delivery
            s1 = [(h.content) for h in sut.replica_state("R1", workflow_id=WF)]
            s2 = [(h.content) for h in sut.replica_state("R2", workflow_id=WF)]
            out.append(self.check("S4.converge", s1 == s2, detail=f"R1={s1} R2={s2}"))

            history = sut.replica_history(workflow_id=WF) if hasattr(sut, "replica_history") else []
            out.append(self.check("S4.lossless", len(history) >= 2,
                                  detail=f"{len(history)} op(s) retained in history"))

            # --- deterministic: same final state across 10 randomised sync orders ---
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
                fa = tuple(h.content for h in sut.replica_state("R1", workflow_id=WF))
                fb = tuple(h.content for h in sut.replica_state("R2", workflow_id=WF))
                finals.add((fa, fb))
            out.append(self.check("S4.deterministic", len(finals) == 1,
                                  detail=f"{len(finals)} distinct final state(s) across {len(orders)} orders"))
        except Unsupported as e:
            for m in ("S4.converge", "S4.deterministic", "S4.lossless"):
                out.append(self.na(m, str(e)))
        return out
