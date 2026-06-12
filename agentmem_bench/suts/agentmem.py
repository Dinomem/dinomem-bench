"""AgentMem SUT adapter — the hosted multi-agent memory service.

Talks to the AgentMem v1 HTTP API (the surface the `agentmem-py` SDK wraps),
using httpx directly so we can observe write-time policy *blocking* (the SDK's
`write` raises on the 4xx block instead of returning the conflict body).

Capabilities mapped from the real API:
  - SCOPES     : write/search carry scope (private/team/global); search enforces visibility
  - CONFLICTS  : POST /v1/memory/conflicts (detectConflicts)
  - POLICIES   : PUT /v1/policies (ignore | planner_wins | timestamp_wins | human_in_loop),
                 enforced AT WRITE TIME (blocks or supersedes)
  - TEMPORAL   : search atTime
NOT VECTOR_CLOCK: the service ticks vector clocks internally and returns them on
reads, but exposes no replica-level write/sync API, so S4's replica protocol
can't be driven → S4 scores N/A. (Worth exposing a replica/sync test hook upstream.)

Config via env:
  AGENTMEM_API_KEY   (required)
  AGENTMEM_BASE_URL  (default: the SDK's hosted endpoint)

Run isolation: every workflow_id is namespaced with a per-setup token so repeated
runs against the shared hosted org don't collide. Cost ($/op) is server-side
(extraction + embeddings) and not observable from the client → reported as 0 with
a caveat in S7.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from ..adapter import SUTAdapter
from ..types import Capability, Conflict, Hit, WriteResult

_DEFAULT_BASE_URL = "https://lwbwcuuzoituanwhekyo.supabase.co/functions/v1/api"


def _parse_ts(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


class AgentMemSUT(SUTAdapter):
    name = "agentmem"
    version = "api-v1 (agentmem-py 0.2.1)"
    capabilities = frozenset(
        {Capability.SCOPES, Capability.CONFLICTS, Capability.POLICIES, Capability.TEMPORAL}
    )

    def setup(self) -> None:
        import httpx  # lazy

        key = os.environ.get("AGENTMEM_API_KEY")
        if not key:
            raise RuntimeError("AGENTMEM_API_KEY is required for the agentmem SUT")
        base = os.environ.get("AGENTMEM_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
        self._http = httpx.Client(
            base_url=base,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        # Namespace workflows so each run is isolated on the shared hosted org.
        self._ns = f"ambench-{uuid.uuid4().hex[:8]}"
        self._blocked: list[dict] = []
        self.last_search_usd = 0.0

    def teardown(self) -> None:
        try:
            self._http.close()
        except Exception:
            pass

    def _wf(self, workflow_id: str | None) -> str | None:
        return None if workflow_id is None else f"{self._ns}:{workflow_id}"

    # --- core ops -----------------------------------------------------------
    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None) -> WriteResult:
        body: dict = {"content": content, "agentId": agent_id, "scope": scope}
        wf = self._wf(workflow_id)
        if wf is not None:
            body["workflowId"] = wf
        if role is not None:
            body["role"] = role
        r = self._http.post("/v1/memory/write", json=body)
        if r.is_success:
            data = r.json()
            return WriteResult(id=str(data.get("writeId", "")), created_at=datetime.now(timezone.utc), usd=0.0)
        # Distinguish a policy block (expected) from a real error.
        try:
            data = r.json()
        except Exception:
            data = {}
        if isinstance(data, dict) and "block" in str(data.get("error", "")).lower():
            self._blocked.append(
                {
                    "type": f"conflict.{data.get('policy', 'blocked')}",
                    "policy": data.get("policy"),
                    "workflow_id": workflow_id,
                    "conflicts": data.get("conflicts", []),
                }
            )
            return WriteResult(id="", created_at=datetime.now(timezone.utc), ok=False)
        r.raise_for_status()  # genuine error -> surfaces as a scenario crash
        return WriteResult(id="", created_at=datetime.now(timezone.utc), ok=False)

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None) -> list[Hit]:
        body: dict = {"query": query, "agentId": agent_id, "topK": top_k}
        wf = self._wf(workflow_id)
        if wf is not None:
            body["workflowId"] = wf
        if at_time is not None:
            body["atTime"] = at_time.astimezone(timezone.utc).isoformat()
        r = self._http.post("/v1/memory/search", json=body)
        r.raise_for_status()
        rows = r.json()
        if isinstance(rows, dict):
            rows = rows.get("results", rows.get("hits", []))
        return [
            Hit(
                id=str(row["id"]),
                content=row["content"],
                agent_id=row.get("agent_id", agent_id),
                scope=row.get("scope", ""),
                created_at=_parse_ts(row.get("created_at")),
                role=row.get("role"),
                score=float(row.get("score", 0.0)),
            )
            for row in rows
        ]

    # --- conflicts / policy -------------------------------------------------
    def check_conflicts(self, content, *, agent_id, workflow_id=None) -> list[Conflict]:
        body: dict = {"content": content, "agentId": agent_id}
        wf = self._wf(workflow_id)
        if wf is not None:
            body["workflowId"] = wf
        r = self._http.post("/v1/memory/conflicts", json=body)
        r.raise_for_status()
        data = r.json()
        return [
            Conflict(
                entity="",
                existing_id=str(c.get("memoryId", "")),
                existing_content=c.get("content", ""),
                new_content=content,
                existing_agent_id=c.get("agentId"),
            )
            for c in data.get("conflicts", [])
        ]

    def set_policy(self, policy, *, workflow_id=None) -> None:
        body = {"policy": policy}
        wf = self._wf(workflow_id)
        if wf is not None:
            body["workflowId"] = wf
        r = self._http.put("/v1/policies", json=body)
        r.raise_for_status()

    def pending_events(self, *, workflow_id=None) -> list[dict]:
        # The client can't observe webhook delivery; the observable HITL signal is
        # a write blocked under the human_in_loop policy (the service refused to
        # auto-resolve and flagged it for a human). That's what we surface here.
        return [
            e
            for e in self._blocked
            if e.get("policy") == "human_in_loop"
            and (workflow_id is None or e.get("workflow_id") == workflow_id)
        ]
