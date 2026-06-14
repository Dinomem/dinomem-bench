"""Cognee SUT adapter — self-host knowledge-graph memory (SQLite+LanceDB+Kuzu).

Cognee ingests text (`add`), builds a knowledge graph (`cognify`, LLM-heavy), then
serves retrieval (`search`). It's graph-RAG, not a multi-agent coordination layer:
no conflict-surfacing API, no policies, no point-in-time temporal, no CRDT. It DOES
isolate by **dataset**, which we use to implement scope:
  team/global → one shared dataset per workflow
  private     → a per-(workflow, agent) dataset; a reader searches the team
                dataset + its own private dataset only.
That gives genuine S3/S5 behaviour via Cognee's native isolation primitive (no
text hacks). Capabilities: {SCOPES}.

Operationally Cognee is SLOW (~tens of seconds per write: add + cognify run LLM
extraction), so S5/S7 are scaled down via AMBENCH_S5_WRITES / AMBENCH_S7_WRITES.
Search uses SearchType.CHUNKS (raw retrieval, verbatim text) — GRAPH_COMPLETION
rewrites the text and would break substring assertions.

Config: OPENAI_API_KEY (used for the LLM + embeddings); ENABLE_BACKEND_ACCESS_CONTROL
is forced off so no user/tenant setup is needed. Self-host, zero infra.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability, Hit, WriteResult


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", s) or "x"


class CogneeSUT(SUTAdapter):
    name = "cognee"
    version = "cognee-1.1.2 (self-host)"
    # NOT SCOPES: with access control off (the zero-setup mode), cognee.search
    # ignores the `datasets` filter and queries the GLOBAL graph — verified by S5
    # (100% cross-workflow leak). Real isolation needs its access-control /
    # multi-tenant layer + per-user setup, which we don't enable here. So scope
    # is untested → S3/S5 N/A (the leak finding lives in the note).
    capabilities = frozenset()
    cost_observable = False  # LLM + embedding cost is real but not instrumented

    def setup(self) -> None:
        os.environ["ENABLE_BACKEND_ACCESS_CONTROL"] = "false"
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for the cognee SUT")
        os.environ.setdefault("LLM_API_KEY", os.environ["OPENAI_API_KEY"])

        # Import cognee + create the event loop ONCE, and reuse across scenarios
        # (cognee's async DB engines bind to a loop; a fresh loop per scenario
        # would break them). setup() just resets data + per-run state each time.
        if not hasattr(self, "_loop"):
            import cognee
            from cognee.modules.search.types import SearchType

            self._cognee = cognee
            self._ST = SearchType
            self._loop = asyncio.new_event_loop()

        self._ns = f"ambench{uuid.uuid4().hex[:8]}"
        self._datasets: set[str] = set()
        self.last_search_usd = 0.0
        try:
            self._run(self._cognee.prune.prune_data())
            self._run(self._cognee.prune.prune_system(metadata=True))
        except Exception:
            pass

    def teardown(self) -> None:
        pass  # keep the loop + cognee globals alive across scenarios

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    # --- scope ↔ dataset mapping --------------------------------------------
    def _team_ds(self, workflow_id: str | None) -> str:
        return f"{self._ns}_{_safe(workflow_id or 'none')}_team"

    def _priv_ds(self, workflow_id: str | None, agent_id: str) -> str:
        return f"{self._ns}_{_safe(workflow_id or 'none')}_{_safe(agent_id)}_priv"

    # --- core ops -----------------------------------------------------------
    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None) -> WriteResult:
        ds = self._priv_ds(workflow_id, agent_id) if scope == "private" else self._team_ds(workflow_id)
        self._run(self._cognee.add(content, dataset_name=ds))
        self._run(self._cognee.cognify(datasets=[ds]))
        self._datasets.add(ds)
        return WriteResult(id=ds, created_at=datetime.now(timezone.utc), usd=0.0)

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None) -> list[Hit]:
        if at_time is not None:
            raise Unsupported("cognee has no temporal (at_time) query")
        # The reader sees the workflow team dataset + its own private dataset only.
        candidates = [self._team_ds(workflow_id), self._priv_ds(workflow_id, agent_id)]
        ds = [d for d in candidates if d in self._datasets]
        if not ds:
            return []
        try:
            res = self._run(
                self._cognee.search(query_text=query, query_type=self._ST.CHUNKS, datasets=ds)
            )
        except Exception:
            return []
        rows = res if isinstance(res, list) else []
        hits: list[Hit] = []
        for r in rows[:top_k]:
            text = r.get("text") if isinstance(r, dict) else (r if isinstance(r, str) else None)
            if not text:
                continue
            hits.append(
                Hit(
                    id=str(r.get("id", "")) if isinstance(r, dict) else "",
                    content=text,
                    agent_id="",
                    scope="",
                    created_at=datetime.now(timezone.utc),
                    score=0.0,
                )
            )
        return hits

    # check_conflicts / set_policy / replica_* inherit Unsupported.
