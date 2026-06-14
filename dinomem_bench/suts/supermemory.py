"""Supermemory SUT adapter — hosted, first-party Python SDK.

Like Mem0, Supermemory's primitives are namespacing (`container_tags`) + semantic
search; it has no conflict/policy/temporal/CRDT API. So it advertises only SCOPES
(workflow via container_tag, private/team via metadata, enforced client-side) and
scores at the floor on S1/S2/S4/S6.

Config: SUPERMEMORY_API_KEY. Cost is the platform subscription (not client-observable).
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability, Hit, WriteResult


class SupermemorySUT(SUTAdapter):
    name = "supermemory"
    version = "supermemory-py-3.46 (hosted)"
    capabilities = frozenset({Capability.SCOPES})  # emulated via container_tag + metadata
    cost_observable = False

    def setup(self) -> None:
        from supermemory import Supermemory  # lazy

        if not os.environ.get("SUPERMEMORY_API_KEY"):
            raise RuntimeError("SUPERMEMORY_API_KEY is required for the supermemory SUT")
        self._c = Supermemory()  # reads SUPERMEMORY_API_KEY from env
        self._ns = f"ambench-{uuid.uuid4().hex[:8]}"
        self.last_search_usd = 0.0

    def teardown(self) -> None:
        try:
            self._c.close()
        except Exception:
            pass

    def _tag(self, workflow_id: str | None) -> str:
        return f"{self._ns}:{workflow_id if workflow_id is not None else 'none'}"

    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None) -> WriteResult:
        resp = self._c.add(
            content=content,
            container_tags=[self._tag(workflow_id)],
            metadata={"scope": scope, "writer": agent_id},
        )
        mem_id = str(getattr(resp, "id", "") or getattr(resp, "memory_id", "") or "")
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
            raise Unsupported("supermemory has no temporal (at_time) query")
        # search.memories is memory search; search.execute is document-chunk search
        # (returns nothing for these short memories).
        resp = self._c.search.memories(q=query, container_tag=self._tag(workflow_id), limit=top_k)
        results = getattr(resp, "results", None) or getattr(resp, "memories", None) or []
        hits: list[Hit] = []
        for r in results:
            d = r.model_dump() if hasattr(r, "model_dump") else (r if isinstance(r, dict) else {})
            meta = d.get("metadata") or {}
            if not self._visible(meta, agent_id):
                continue
            content = d.get("memory") or d.get("chunk") or ""
            hits.append(
                Hit(
                    id=str(d.get("id", "")),
                    content=content,
                    agent_id=meta.get("writer") or "",
                    scope=meta.get("scope") or "",
                    created_at=datetime.now(timezone.utc),
                    score=float(d.get("similarity") or d.get("score") or 0.0),
                )
            )
        return hits

    # check_conflicts / set_policy / replica_* inherit Unsupported.
