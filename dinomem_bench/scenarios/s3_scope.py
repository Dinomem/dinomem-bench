"""S3 — Scope enforcement. DESIGN §4 S3."""

from __future__ import annotations

from ..adapter import SUTAdapter
from ..types import Capability
from .base import Scenario, MetricResult

WF = "s3-wf"
WF_OTHER = "s3-wf-other"


class S3Scope(Scenario):
    id = "S3"
    slug = "s3_scope"
    title = "Scope enforcement"
    requires = frozenset({Capability.SCOPES})

    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        out: list[MetricResult] = []
        if not sut.supports(Capability.SCOPES):
            for m in ("S3.isolated", "S3.team_visible", "S3.cross_workflow"):
                out.append(self.na(m, "no scope capability"))
            return out

        # A writes a private memory; B (different agent, same workflow) searches.
        # Settle as A first so the memory is genuinely indexed — otherwise an
        # async SUT could "pass" isolation just because nothing was indexed yet.
        sut.write("Apikey is sk-secret-123.", agent_id="agent-a", scope="private", workflow_id=WF)
        self.settle(sut, query="Apikey", agent_id="agent-a", workflow_id=WF, needle="apikey")
        b_hits = sut.search("Apikey", agent_id="agent-b", workflow_id=WF)
        out.append(self.check("S3.isolated", len(b_hits) == 0,
                              detail=f"B saw {len(b_hits)} hit(s) of A's private memory"))

        # A re-writes the same fact at team scope; B should now see it. Settle as B
        # (who can only see team scope) so we wait for the team memory specifically.
        sut.write("Apikey is sk-secret-123.", agent_id="agent-a", scope="team", workflow_id=WF)
        self.settle(sut, query="Apikey", agent_id="agent-b", workflow_id=WF, needle="apikey")
        b_hits2 = sut.search("Apikey", agent_id="agent-b", workflow_id=WF)
        out.append(self.check("S3.team_visible", len(b_hits2) > 0,
                              detail=f"B saw {len(b_hits2)} hit(s) after team re-write"))

        # A reader in a different workflow must see none of workflow-A's facts.
        x_hits = sut.search("Apikey", agent_id="agent-x", workflow_id=WF_OTHER)
        out.append(self.check("S3.cross_workflow", len(x_hits) == 0,
                              detail=f"cross-workflow reader saw {len(x_hits)} hit(s) (must be 0)"))
        return out
