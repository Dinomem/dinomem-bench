"""DinoMem SUT adapter — the hosted multi-agent memory service.

Talks to the DinoMem v1 HTTP API (the surface the `dinomem-py` SDK wraps),
using httpx directly so we can observe write-time policy *blocking* (the SDK's
`write` raises on the 4xx block instead of returning the conflict body).

Capabilities mapped from the real API:
  - SCOPES     : write/search carry scope (private/team/global); search enforces visibility
  - CONFLICTS  : POST /v1/memory/conflicts (detectConflicts)
  - POLICIES   : PUT /v1/policies (ignore | planner_wins | timestamp_wins | human_in_loop),
                 enforced AT WRITE TIME (blocks or supersedes)
  - TEMPORAL   : search atTime
  - VECTOR_CLOCK : CRDT V3 ships a black-box replica/sync API
                 (POST /v1/crdt/replicas/{rid}/write, POST .../sync, GET .../state).
                 Each write requires an evidenceId (UUID of an existing memory_event
                 in this org, FR-P0-3 provenance requirement) — the adapter creates
                 a backing /v1/memory/write first and uses its writeId automatically.
                 The op log is durable + org-scoped and a replica's state is the
                 pure CvRDT merge of the ops it knows; convergence is property-
                 tested in the core
                 (agentmem/supabase/functions/api/lib/crdt-merge.test.ts:
                 order-independence, the CvRDT laws, no-lost-writes vs an
                 independent brute force, partial-sync convergence, LWW ablation).
                 So S4 is now drivable end-to-end against DinoMem — no longer N/A.
                 (Earlier versions of this adapter advertised NOT VECTOR_CLOCK:
                 vector clocks ticked internally but there was no replica/sync
                 surface a convergence test could drive. CRDT V3 added it.)

Config via env:
  DINOMEM_API_KEY   (required)
  DINOMEM_BASE_URL  (default: the SDK's hosted endpoint)

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
from .fake import parse_entity  # pure stdlib helper: content -> (key, value)

_DEFAULT_BASE_URL = "https://lwbwcuuzoituanwhekyo.supabase.co/functions/v1/api"


def _parse_ts(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    """The API's Zod `.datetime()` accepts only 'Z', not '+00:00' offsets."""
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _raise(r) -> None:
    """Raise with the response body included, so a crash detail is debuggable."""
    raise RuntimeError(f"HTTP {r.status_code} {r.request.method} {r.request.url.path}: {r.text[:300]}")


class DinoMemSUT(SUTAdapter):
    name = "dinomem"
    version = "api-v1 (dinomem-py 0.2.1)"
    capabilities = frozenset(
        {
            Capability.SCOPES,
            Capability.CONFLICTS,
            Capability.POLICIES,
            Capability.TEMPORAL,
            Capability.VECTOR_CLOCK,  # CRDT V3 replica/sync API (see module docstring)
        }
    )
    cost_observable = False  # hosted; extraction + embeddings billed server-side

    def setup(self) -> None:
        import httpx  # lazy

        # back-compat: fall back to the old AGENTMEM_* env names so existing users don't break
        key = os.environ.get("DINOMEM_API_KEY") or os.environ.get("AGENTMEM_API_KEY")
        if not key:
            raise RuntimeError("DINOMEM_API_KEY is required for the dinomem SUT")
        # back-compat: old env name
        base = os.environ.get("DINOMEM_BASE_URL") or os.environ.get("AGENTMEM_BASE_URL") or _DEFAULT_BASE_URL
        base = base.rstrip("/")
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
        _raise(r)  # genuine error -> surfaces as a scenario crash (with body)

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None) -> list[Hit]:
        body: dict = {"query": query, "agentId": agent_id, "topK": top_k}
        wf = self._wf(workflow_id)
        if wf is not None:
            body["workflowId"] = wf
        if at_time is not None:
            body["atTime"] = _iso_z(at_time)
        r = self._http.post("/v1/memory/search", json=body)
        if not r.is_success:
            _raise(r)
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
        if not r.is_success:
            _raise(r)
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
        if not r.is_success:
            _raise(r)

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

    # --- CRDT / replica extension (S4) — CRDT V3 black-box replica API ---------
    # The core convergence engine + its CvRDT property suite live in
    # agentmem/supabase/functions/api/lib/crdt-merge{,.test}.ts; these endpoints
    # are the thin org-scoped HTTP shell the benchmark drives (routes/crdt.ts).
    def _rid(self, replica: str) -> str:
        """Namespace the replica id with this run's token so concurrent runs on
        the shared hosted org never collide on a replica."""
        return f"{self._ns}.{replica}"

    def _key(self, key: str, workflow_id: str | None) -> str:
        """Namespace the register key per workflow for the same isolation reason."""
        wf = self._wf(workflow_id)
        return key if wf is None else f"{wf}:{key}"

    def replica_write(self, replica, content, *, agent_id, workflow_id=None, vclock=None) -> WriteResult:
        # The replica API is keyed (LWW-Register), so split the scenario's
        # "X is Y" content into (key, value) the same way FakeSUT does. The server
        # assigns the vector clock itself (increments node=replica_id), so the
        # scenario's hint `vclock` is intentionally not forwarded — the engine is
        # the source of truth for causality.
        #
        # The CRDT write API (FR-P0-3) requires an evidenceId — a UUID referencing
        # an existing memory event in this org. We create a backing memory write
        # first and use its writeId as the provenance reference. The backing write
        # goes into the same workflow namespace as the CRDT op.
        key, value = parse_entity(content)
        wf_body: dict = {"content": content, "agentId": agent_id, "scope": "team"}
        wf = self._wf(workflow_id)
        if wf is not None:
            wf_body["workflowId"] = wf
        backing = self._http.post("/v1/memory/write", json=wf_body)
        if not backing.is_success:
            _raise(backing)
        evidence_id = str(backing.json().get("writeId", ""))
        if not evidence_id:
            raise RuntimeError("replica_write: backing /write did not return a writeId")
        body = {"key": self._key(key, workflow_id), "value": value, "agentId": agent_id, "evidenceId": evidence_id}
        r = self._http.post(f"/v1/crdt/replicas/{self._rid(replica)}/write", json=body)
        if not r.is_success:
            _raise(r)
        op = (r.json() or {}).get("op", {})
        return WriteResult(
            id=str(op.get("opId", "")),
            created_at=_parse_ts(op.get("ts")),
            ok=True,
        )

    def replica_sync(self, order) -> None:
        # Each (frm, to) step makes `to` learn every op `frm` knows. Idempotent
        # server-side, so repeating / reversing the order is safe and converges.
        for frm, to in order:
            r = self._http.post(
                f"/v1/crdt/replicas/{self._rid(to)}/sync",
                json={"from": self._rid(frm)},
            )
            if not r.is_success:
                _raise(r)

    def replica_state(self, replica, *, workflow_id=None) -> list[Hit]:
        r = self._http.get(f"/v1/crdt/replicas/{self._rid(replica)}/state")
        if not r.is_success:
            _raise(r)
        rows = (r.json() or {}).get("state", [])
        prefix = self._wf(workflow_id)
        out: list[Hit] = []
        for row in rows:
            raw_key = str(row.get("key", ""))
            if prefix is not None:
                if not raw_key.startswith(f"{prefix}:"):
                    continue  # belongs to another workflow's namespace
                key = raw_key[len(prefix) + 1 :]
            else:
                key = raw_key
            value = row.get("value", "")
            out.append(
                Hit(
                    id=str(row.get("opId", "")),
                    # Reconstruct a stable, comparable content string from the
                    # converged (key,value). Two replicas that converged to the
                    # same register produce byte-identical content here, which is
                    # exactly what S4.converge compares.
                    content=f"{key.capitalize()} is {value}.",
                    agent_id=str(row.get("agentId", "")),
                    scope="team",
                    created_at=datetime.now(timezone.utc),
                    score=1.0,
                )
            )
        out.sort(key=lambda h: h.content)
        return out
