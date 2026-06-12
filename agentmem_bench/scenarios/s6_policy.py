"""S6 — Policy fidelity. DESIGN §4 S6.

Run the S1 conflict under each resolution policy and assert the read matches the
policy's documented semantics.
"""

from __future__ import annotations

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability
from .base import Scenario, MetricResult

WF = "s6-wf"


class S6Policy(Scenario):
    id = "S6"
    slug = "s6_policy"
    title = "Policy fidelity"
    requires = frozenset({Capability.POLICIES})

    def _read_under(self, sut: SUTAdapter, policy: str) -> list[str]:
        """Configure the policy FIRST, then create the conflict, then read — so it
        works for both write-time enforcers and read-time resolvers."""
        sut.setup()
        sut.set_policy(policy, workflow_id=WF)
        sut.write("Deadline is Friday.", agent_id="planner", scope="team", role="planner", workflow_id=WF)
        self.settle(sut, query="Deadline", agent_id="planner", workflow_id=WF, needle="friday")
        sut.write("Deadline is Monday.", agent_id="executor", scope="team", role="executor", workflow_id=WF)
        return [h.content.lower() for h in sut.search("Deadline", agent_id="reader", workflow_id=WF)]

    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        out: list[MetricResult] = []
        if not sut.supports(Capability.POLICIES):
            for p in ("ignore", "timestamp_wins", "planner_wins", "human_in_loop"):
                out.append(self.na(f"P.{p}.correct", "no policy capability"))
            out.append(self.na("P.human_in_loop.surfaced", "no policy capability"))
            return out

        try:
            ig = self._read_under(sut, "ignore")
            out.append(self.check("P.ignore.correct",
                                  any("friday" in v for v in ig) and any("monday" in v for v in ig),
                                  detail=f"ignore -> {ig} (expect both)"))

            tw = self._read_under(sut, "timestamp_wins")
            out.append(self.check("P.timestamp_wins.correct",
                                  any("monday" in v for v in tw) and not any("friday" in v for v in tw),
                                  detail=f"timestamp_wins -> {tw} (expect Monday)"))

            pw = self._read_under(sut, "planner_wins")
            out.append(self.check("P.planner_wins.correct",
                                  any("friday" in v for v in pw) and not any("monday" in v for v in pw),
                                  detail=f"planner_wins -> {pw} (expect Friday)"))

            # human_in_loop: the system must NOT silently auto-resolve — it must
            # surface the conflict for a human. The read outcome is implementation-
            # specific (keep-both vs block-the-write), so "correct" = surfaced OR
            # both retained; the unambiguous signal is .surfaced.
            hil = self._read_under(sut, "human_in_loop")
            try:
                events = sut.pending_events(workflow_id=WF)
                surfaced = any(str(e.get("type", "")).startswith("conflict") for e in events)
            except Unsupported:
                events, surfaced = [], False
            both = any("friday" in v for v in hil) and any("monday" in v for v in hil)
            out.append(self.check("P.human_in_loop.correct", surfaced or both,
                                  detail=f"human_in_loop -> read {hil}, surfaced={surfaced}"))
            out.append(self.check("P.human_in_loop.surfaced", surfaced,
                                  detail=f"{len(events)} event(s) emitted"))
        except Unsupported as e:
            for p in ("ignore", "timestamp_wins", "planner_wins", "human_in_loop"):
                out.append(self.na(f"P.{p}.correct", str(e)))
        return out
