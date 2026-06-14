"""Zep SUT adapter — hosted temporal knowledge graph (Graphiti).

Zep is the one SUT that might actually fill S2: it extracts facts (graph edges)
with full bitemporal validity (`valid_at` / `invalid_at`) and invalidates a fact
when a later one contradicts it. We set `created_at` on `graph.add` (so we control
the S2 timestamps) and answer `at_time` by filtering edges on their validity
interval — a genuine point-in-time query.

Zep is graph-centric (a `graph_id` is the isolation unit) with no per-agent scope,
so it advertises only TEMPORAL. workflow_id -> graph_id (namespaced per run).
Facts are extracted asynchronously, so scenarios rely on `Scenario.settle()`.

Capabilities: {TEMPORAL}. Cost is the platform subscription (not client-observable).
Config: ZEP_API_KEY.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability, Hit, WriteResult

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _parse(dt: str | None) -> datetime | None:
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except ValueError:
        return None


class ZepSUT(SUTAdapter):
    name = "zep"
    version = "zep-cloud-3.23 (hosted)"
    capabilities = frozenset({Capability.TEMPORAL})
    cost_observable = False

    def setup(self) -> None:
        from zep_cloud.client import Zep  # lazy

        key = os.environ.get("ZEP_API_KEY")
        if not key:
            raise RuntimeError("ZEP_API_KEY is required for the zep SUT")
        self._z = Zep(api_key=key)
        self._ns = f"ambench{uuid.uuid4().hex[:8]}"
        self._graphs: set[str] = set()
        # logical clock: 60s per write, so successive writes get distinct, ordered
        # episode timestamps (mirrors DESIGN S2's T1 = T0 + 60s).
        self._tick = 0
        self.last_search_usd = 0.0

    def teardown(self) -> None:
        pass

    def _gid(self, workflow_id: str | None) -> str:
        return f"{self._ns}-{workflow_id if workflow_id is not None else 'none'}"

    def _ensure_graph(self, gid: str) -> None:
        if gid in self._graphs:
            return
        try:
            self._z.graph.create(graph_id=gid)
        except Exception:
            pass  # already exists / created concurrently
        self._graphs.add(gid)

    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None) -> WriteResult:
        gid = self._gid(workflow_id)
        self._ensure_graph(gid)
        created = _BASE + timedelta(seconds=60 * self._tick)
        self._tick += 1
        self._z.graph.add(
            graph_id=gid,
            type="text",
            data=content,
            created_at=created.isoformat().replace("+00:00", "Z"),
        )
        return WriteResult(id=f"{gid}:{self._tick}", created_at=created, usd=0.0)

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None) -> list[Hit]:
        gid = self._gid(workflow_id)
        try:
            res = self._z.graph.search(query=query, graph_id=gid, scope="edges", limit=max(top_k, 10))
        except Exception as e:
            raise Unsupported(f"zep search failed: {e}") from e
        edges = getattr(res, "edges", None) or []
        hits: list[Hit] = []
        for e in edges:
            fact = getattr(e, "fact", None) or ""
            valid_at = _parse(getattr(e, "valid_at", None))
            invalid_at = _parse(getattr(e, "invalid_at", None))
            if at_time is not None:
                at = at_time if at_time.tzinfo else at_time.replace(tzinfo=timezone.utc)
                # valid at `at` iff valid_at <= at < invalid_at
                if valid_at is not None and valid_at > at:
                    continue
                if invalid_at is not None and at >= invalid_at:
                    continue
            else:
                # current state: drop facts already invalidated
                if invalid_at is not None:
                    continue
            hits.append(
                Hit(
                    id=str(getattr(e, "uuid_", "") or ""),
                    content=fact,
                    agent_id="",
                    scope="",
                    created_at=valid_at or _parse(getattr(e, "created_at", None)) or datetime.now(timezone.utc),
                    score=float(getattr(e, "score", 0.0) or 0.0),
                )
            )
        return hits[:top_k]

    # check_conflicts / set_policy / replica_* inherit Unsupported. Zep auto-
    # invalidates contradicting facts but exposes no conflict-surfacing API, so
    # S1 detection / S6 policies are N/A — the resolution shows up via S2 instead.
