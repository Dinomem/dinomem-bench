"""S1 — Contradictory writes (basic). DESIGN §4 S1.

Two agents in one workflow write contradictory facts about the same entity.
"""

from __future__ import annotations

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability
from .base import Scenario, MetricResult

WF = "s1-wf"


class S1Contradictory(Scenario):
    id = "S1"
    slug = "s1_contradictory"
    title = "Contradictory writes (basic)"
    requires = frozenset({Capability.CONFLICTS, Capability.POLICIES})

    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        out: list[MetricResult] = []

        # Set the policy FIRST, before the writes it governs. Systems that enforce
        # at write time (e.g. block the conflicting write) and systems that resolve
        # at read time both then exercise the same configured policy. (Setting it
        # after the writes would no-op against a write-time enforcer.)
        policies_ok = sut.supports(Capability.POLICIES)
        if policies_ok:
            try:
                sut.set_policy("planner_wins", workflow_id=WF)
            except Unsupported:
                policies_ok = False

        sut.write("Deadline is Friday.", agent_id="planner", scope="team", role="planner", workflow_id=WF)

        # C1.detected — does the system surface the conflict before the 2nd write?
        if sut.supports(Capability.CONFLICTS):
            try:
                conflicts = sut.check_conflicts("Deadline is Monday.", agent_id="executor", workflow_id=WF)
                out.append(self.check("C1.detected", len(conflicts) > 0,
                                      detail=f"{len(conflicts)} conflict(s) surfaced"))
            except Unsupported as e:
                out.append(self.na("C1.detected", str(e)))
        else:
            out.append(self.na("C1.detected", "no conflict-detection capability"))

        # The executor's conflicting write. Under planner_wins a write-time enforcer
        # blocks it; a read-time resolver stores it and filters on read. Either way
        # the read below should return only the planner's fact.
        sut.write("Deadline is Monday.", agent_id="executor", scope="team", role="executor", workflow_id=WF)

        # C1.resolved — under planner_wins, retrieval returns only the planner's fact.
        if policies_ok:
            hits = sut.search("Deadline", agent_id="reader", workflow_id=WF)
            vals = [h.content.lower() for h in hits]
            only_planner = any("friday" in v for v in vals) and not any("monday" in v for v in vals)
            out.append(self.check("C1.resolved", only_planner, detail=f"planner_wins -> {vals}"))
        else:
            out.append(self.na("C1.resolved", "no policy capability"))

        # C1.consistent — two parallel readers see the same fact.
        h1 = sut.search("Deadline", agent_id="reader-a", workflow_id=WF)
        h2 = sut.search("Deadline", agent_id="reader-b", workflow_id=WF)
        same = sorted(h.content for h in h1) == sorted(h.content for h in h2)
        out.append(self.check("C1.consistent", same,
                              detail=f"a={[h.content for h in h1]} b={[h.content for h in h2]}"))
        return out
