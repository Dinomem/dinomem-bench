"""pgvector baseline SUT — the floor (DESIGN §3).

Just INSERT + cosine-similarity SELECT TOP K over a Postgres table, with
OpenAI embeddings and NO extraction. Its whole point is to expose which
scenarios actually need a memory system vs which are pure retrieval/filtering:
it can enforce scope + workflow isolation with a WHERE clause (so it PASSES
S3/S5), but it has no conflict detection, policies, temporal validity, or CRDT
semantics (so those metrics score N/A).

Config via env:
  DATABASE_URL    Postgres DSN (default postgresql://postgres:bench@localhost:5433/bench)
  OPENAI_API_KEY  for embeddings
  PGVECTOR_EMBED_MODEL  (default text-embedding-3-small)

Deps (optional extra): psycopg[binary], openai.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from ..adapter import SUTAdapter, Unsupported
from ..types import Capability, Hit, WriteResult

_DEFAULT_DSN = "postgresql://postgres:bench@localhost:5433/bench"
_TABLE = "amb_memories"
# Pinned per DESIGN §6 (no `latest`). 3-small is 1536-dim; price $0.02 / 1M tokens.
_EMBED_MODEL = os.environ.get("PGVECTOR_EMBED_MODEL", "text-embedding-3-small")
_EMBED_DIMS = 1536
_USD_PER_1M_TOKENS = 0.02


def _vec_literal(emb: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in emb) + "]"


class PgvectorSUT(SUTAdapter):
    name = "pgvector"
    version = f"pg16+{_EMBED_MODEL}"
    capabilities = frozenset({Capability.SCOPES})  # WHERE-clause filtering only

    def setup(self) -> None:
        import psycopg  # lazy: only when this SUT is selected
        from openai import OpenAI

        self._oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        dsn = os.environ.get("DATABASE_URL", _DEFAULT_DSN)
        # Postgres may still be starting; retry the first connect briefly.
        last = None
        for _ in range(20):
            try:
                self._conn = psycopg.connect(dsn, autocommit=True)
                break
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(0.5)
        else:
            raise RuntimeError(f"could not connect to Postgres at {dsn}: {last}")

        self.last_search_usd = 0.0
        c = self._conn
        c.execute("create extension if not exists vector")
        c.execute(f"drop table if exists {_TABLE}")
        c.execute(
            f"""
            create table {_TABLE} (
                id          bigserial primary key,
                content     text not null,
                agent_id    text not null,
                role        text,
                scope       text not null,
                workflow_id text,
                created_at  timestamptz not null default now(),
                embedding   vector({_EMBED_DIMS})
            )
            """
        )
        c.execute(
            f"create index on {_TABLE} using ivfflat (embedding vector_cosine_ops) with (lists = 100)"
        )

    def teardown(self) -> None:
        try:
            self._conn.execute(f"drop table if exists {_TABLE}")
            self._conn.close()
        except Exception:
            pass

    # --- embeddings ---------------------------------------------------------
    def _embed(self, text: str) -> tuple[list[float], float]:
        resp = self._oai.embeddings.create(model=_EMBED_MODEL, input=text)
        usd = (resp.usage.total_tokens / 1_000_000) * _USD_PER_1M_TOKENS
        return resp.data[0].embedding, usd

    # --- core ops -----------------------------------------------------------
    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None) -> WriteResult:
        emb, usd = self._embed(content)
        row = self._conn.execute(
            f"""insert into {_TABLE} (content, agent_id, role, scope, workflow_id, embedding)
                values (%s,%s,%s,%s,%s,%s::vector) returning id, created_at""",
            (content, agent_id, role, scope, workflow_id, _vec_literal(emb)),
        ).fetchone()
        return WriteResult(id=str(row[0]), created_at=row[1], usd=usd)

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None) -> list[Hit]:
        if at_time is not None:
            raise Unsupported("pgvector baseline has no temporal (at_time) query")
        emb, usd = self._embed(query)
        self.last_search_usd = usd
        # Scope visibility as a WHERE clause: global is universal; team/private
        # require same workflow; private additionally requires same agent.
        rows = self._conn.execute(
            f"""
            select id, content, agent_id, role, scope, created_at
            from {_TABLE}
            where (
                scope = 'global'
                or (workflow_id is not distinct from %(wf)s and (
                        scope = 'team'
                        or (scope = 'private' and agent_id = %(aid)s)
                   ))
            )
            order by embedding <=> %(q)s::vector
            limit %(k)s
            """,
            {"wf": workflow_id, "aid": agent_id, "q": _vec_literal(emb), "k": top_k},
        ).fetchall()
        return [
            Hit(id=str(r[0]), content=r[1], agent_id=r[2], role=r[3], scope=r[4], created_at=r[5], score=1.0)
            for r in rows
        ]

    # check_conflicts / set_policy / replica_* inherit Unsupported from the base
    # class — a raw vector store has none of that machinery (the whole point).
