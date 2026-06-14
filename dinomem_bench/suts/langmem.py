"""LangMem SUT adapter — LangChain/LangGraph long-term memory (a self-host floor).

LangMem is built on a LangGraph `BaseStore` with semantic search. The DESIGN
lists it as a floor (alongside pgvector). We back it with `InMemoryStore` + an
OpenAI embedding index (the DESIGN's "LangGraph backend, OpenAI embeddings",
minus the Postgres infra — same semantics, zero infra). Namespaces give workflow
isolation; private/team scope is held in the value + enforced client-side.

No conflict/policy/temporal/CRDT API → those are N/A. Capabilities: {SCOPES}.
Synchronous + in-process (the only latency is the OpenAI embedding call), so no
async-indexing settle is needed.

Config (override order: env > configs/langmem.json > default — see config.py /
CONTRIBUTING.md): OPENAI_API_KEY; `embed_model` (env `LANGMEM_EMBED_MODEL`).
Optional extra: langmem, langchain-openai.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from ..adapter import SUTAdapter, Unsupported
from ..config import load as load_config
from ..models import OPENAI_EMBED_3_SMALL
from ..types import Capability, Hit, WriteResult

# Pinned model dims from the central registry (DESIGN §6, no `latest`). The model
# string is config/env-overridable; dims/price assume text-embedding-3-small.
_EMBED_DIMS = OPENAI_EMBED_3_SMALL.dims


class LangMemSUT(SUTAdapter):
    name = "langmem"
    version = f"langmem-0.0.30 + langgraph InMemoryStore ({OPENAI_EMBED_3_SMALL.name})"
    capabilities = frozenset({Capability.SCOPES})
    cost_observable = False  # OpenAI embedding cost (not instrumented here)

    def setup(self) -> None:
        from langchain_openai import OpenAIEmbeddings  # lazy
        from langgraph.store.memory import InMemoryStore

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for the langmem SUT")
        cfg = load_config("langmem")
        embed_model = cfg.get("embed_model", OPENAI_EMBED_3_SMALL.name, env="LANGMEM_EMBED_MODEL")
        self.version = f"langmem-0.0.30 + langgraph InMemoryStore ({embed_model})"
        emb = OpenAIEmbeddings(model=embed_model)
        # Semantic index over the "content" field — this is what makes store.search
        # a vector search rather than a key lookup.
        self._store = InMemoryStore(index={"dims": _EMBED_DIMS, "embed": emb, "fields": ["content"]})
        self._ns = f"ambench-{uuid.uuid4().hex[:8]}"
        self._k = 0
        self.last_search_usd = 0.0

    def teardown(self) -> None:
        pass

    def _namespace(self, workflow_id: str | None) -> tuple[str, str]:
        return (self._ns, workflow_id if workflow_id is not None else "none")

    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None) -> WriteResult:
        self._k += 1
        key = f"m{self._k}"
        self._store.put(
            self._namespace(workflow_id),
            key,
            {"content": content, "scope": scope, "writer": agent_id},
        )
        return WriteResult(id=key, created_at=datetime.now(timezone.utc), usd=0.0)

    def _visible(self, value: dict, reader_agent: str) -> bool:
        scope = (value or {}).get("scope", "team")
        if scope in ("team", "global"):
            return True
        if scope == "private":
            return (value or {}).get("writer") == reader_agent
        return True

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None) -> list[Hit]:
        if at_time is not None:
            raise Unsupported("langmem has no temporal (at_time) query")
        items = self._store.search(self._namespace(workflow_id), query=query, limit=top_k)
        hits: list[Hit] = []
        for it in items:
            value = getattr(it, "value", None) or {}
            if not self._visible(value, agent_id):
                continue
            hits.append(
                Hit(
                    id=str(getattr(it, "key", "")),
                    content=value.get("content", ""),
                    agent_id=value.get("writer", "") or "",
                    scope=value.get("scope", "") or "",
                    created_at=datetime.now(timezone.utc),
                    score=float(getattr(it, "score", 0.0) or 0.0),
                )
            )
        return hits

    # check_conflicts / set_policy / replica_* inherit Unsupported.
