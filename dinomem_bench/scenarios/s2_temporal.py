"""S2 — Temporal validity. DESIGN §4 S2.

One agent writes F1 at T0, then a contradicting F2 at T1. Reader queries at_time.
We use the timestamps the SUT assigns to each write (WriteResult.created_at),
not wall-clock sleeps, so the test is fast and deterministic.
"""

from __future__ import annotations

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability
from .base import Scenario, MetricResult

WF = "s2-wf"


class S2Temporal(Scenario):
    id = "S2"
    slug = "s2_temporal"
    title = "Temporal validity"
    requires = frozenset({Capability.TEMPORAL})

    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        out: list[MetricResult] = []
        r1 = sut.write("Project status is green.", agent_id="lead", scope="team", workflow_id=WF)
        r2 = sut.write("Project status is red.", agent_id="lead", scope="team", workflow_id=WF)

        # T1.bitemporal — does the system support at_time at all? This is a
        # descriptive capability (DESIGN: "Y/N — many do not"), not a correctness
        # judgment, so it's INFO: absence is a fact, not a failure.
        from .base import yn
        supports = sut.supports(Capability.TEMPORAL)
        out.append(self.info("T1.bitemporal", yn(supports), detail="at_time query support"))
        if not supports:
            out.append(self.na("T1.t0", "no temporal capability"))
            out.append(self.na("T1.t1", "no temporal capability"))
            return out

        # Wait for the system to process the contradiction (e.g. Zep extracts facts
        # + invalidates the old one asynchronously, ~tens of seconds) — once "red"
        # is the current fact, the temporal state has settled. Instant for
        # in-process SUTs. Then run the point-in-time queries.
        self.settle(sut, query="Project status", agent_id="reader", workflow_id=WF, needle="red")
        try:
            at_t0 = sut.search("Project status", agent_id="reader", workflow_id=WF, at_time=r1.created_at)
            at_t1 = sut.search("Project status", agent_id="reader", workflow_id=WF, at_time=r2.created_at)
        except Unsupported as e:
            out.append(self.na("T1.t0", str(e)))
            out.append(self.na("T1.t1", str(e)))
            return out

        v0 = [h.content.lower() for h in at_t0]
        v1 = [h.content.lower() for h in at_t1]
        out.append(self.check("T1.t0", any("green" in v for v in v0) and not any("red" in v for v in v0),
                              detail=f"at_time=T0 -> {v0}"))
        out.append(self.check("T1.t1", any("red" in v for v in v1) and not any("green" in v for v in v1),
                              detail=f"at_time=T1 -> {v1}"))
        return out
