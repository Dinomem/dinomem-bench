"""Mem0 SUT adapter — the category-leading managed memory service (hosted).

Uses the `mem0ai` Python `MemoryClient`. Mem0's primitives are `user_id` /
`agent_id` namespacing + semantic search; it has **no** API for conflict
detection, resolution policies, temporal (`at_time`) queries, or vector-clock
CRDT. So on this multi-agent benchmark Mem0 advertises only SCOPES — and even
that is emulated by the adapter via metadata filtering (Mem0 stores no scope
label), exactly like the pgvector floor. That parity is the finding: a managed
memory system that ships none of the coordination primitives scores at the floor
on S1/S2/S4/S6.

Mapping:
  workflow_id -> Mem0 user_id (the isolation boundary; namespaced per run)
  agent_id    -> Mem0 agent_id + metadata.writer
  scope       -> metadata.scope (private/team/global), enforced client-side on read
  write       -> add(..., infer=False)  (verbatim, synchronous store)

Config: MEM0_API_KEY (hosted free tier). Cost is the platform subscription, not
client-observable per-op -> reported 0 in S7 (latency is measured).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability, Hit, WriteResult


class Mem0SUT(SUTAdapter):
    name = "mem0"
    version = "mem0ai-2.0.5 (hosted)"
    capabilities = frozenset({Capability.SCOPES})  # emulated via metadata filtering
    cost_observable = False  # hosted; cost is the platform subscription

    def setup(self) -> None:
        from mem0 import MemoryClient  # lazy

        if not os.environ.get("MEM0_API_KEY"):
            raise RuntimeError("MEM0_API_KEY is required for the mem0 SUT")
        self._c = MemoryClient()  # reads MEM0_API_KEY from env
        self._ns = f"ambench-{uuid.uuid4().hex[:8]}"
        self.last_search_usd = 0.0

    def teardown(self) -> None:
        pass

    def _uid(self, workflow_id: str | None) -> str:
        return f"{self._ns}:{workflow_id if workflow_id is not None else 'none'}"

    # --- core ops -----------------------------------------------------------
    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None) -> WriteResult:
        resp = self._c.add(
            [{"role": "user", "content": content}],
            user_id=self._uid(workflow_id),
            agent_id=agent_id,
            metadata={"scope": scope, "writer": agent_id},
            infer=False,  # verbatim, synchronous store (no async extraction)
        )
        results = resp.get("results", []) if isinstance(resp, dict) else []
        mem_id = str(results[0]["id"]) if results else ""
        return WriteResult(id=mem_id, created_at=datetime.now(timezone.utc), usd=0.0)

    def _visible(self, meta: dict, reader_agent: str) -> bool:
        scope = (meta or {}).get("scope", "team")
        if scope in ("team", "global"):
            return True
        if scope == "private":
            return (meta or {}).get("writer") == reader_agent
        return True

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None) -> list[Hit]:
        if at_time is not None:
            raise Unsupported("mem0 has no temporal (at_time) query")
        resp = self._c.search(query, filters={"user_id": self._uid(workflow_id)}, top_k=top_k)
        rows = resp.get("results", resp) if isinstance(resp, dict) else resp
        hits: list[Hit] = []
        for r in rows or []:
            meta = r.get("metadata") or {}
            if not self._visible(meta, agent_id):
                continue  # scope enforcement (emulated; Mem0 stores no scope label)
            hits.append(
                Hit(
                    id=str(r.get("id", "")),
                    content=r.get("memory", ""),
                    agent_id=meta.get("writer") or r.get("agent_id") or "",
                    scope=meta.get("scope", ""),
                    created_at=datetime.now(timezone.utc),
                    score=float(r.get("score", 0.0)),
                )
            )
        return hits

    # check_conflicts / set_policy / replica_* inherit Unsupported — Mem0 exposes
    # none of these (its dedup is silent + internal, with no surfacing API).
