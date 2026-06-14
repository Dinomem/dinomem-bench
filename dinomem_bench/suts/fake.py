"""FakeSUT — an in-memory reference memory system.

This is NOT a system under test in the published comparison. It exists to (a)
exercise the harness end-to-end and (b) serve as the "gold-standard correct"
implementation: a memory system that does everything the scenarios ask for, so
a passing FakeSUT means the scenarios + assertions themselves are sound.

It implements, deterministically and without any LLM/embeddings:
  - scope enforcement (private/team/global) + workflow isolation
  - conflict detection between cross-agent writes about the same entity
  - resolution policies (ignore / timestamp_wins / planner_wins / human_in_loop)
  - bitemporal validity (self-updates supersede; at_time queries)
  - a vector-clock CRDT replica model with deterministic conflict resolution

Entity extraction is a deterministic heuristic ("X is Y" -> entity X, value Y),
standing in for the LLM extraction a real system would do. The scenario fixtures
are written to that shape on purpose.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..adapter import SUTAdapter
from ..types import Capability, Conflict, Hit, WriteResult

_EPOCH = datetime(2026, 1, 1, 0, 0, 0)


def parse_entity(content: str) -> tuple[str, str]:
    """'Deadline is Friday.' -> ('deadline', 'friday'). Falls back to the whole
    normalized string as both entity and value when there's no 'is'/':' split."""
    norm = content.strip().rstrip(".").strip()
    m = re.split(r"\s+is\s+|:\s*", norm, maxsplit=1, flags=re.IGNORECASE)
    if len(m) == 2 and m[0]:
        return m[0].strip().lower(), m[1].strip().lower()
    low = norm.lower()
    return low, low


@dataclass
class _Rec:
    id: str
    content: str
    agent_id: str
    role: str | None
    scope: str
    workflow_id: str | None
    created_at: datetime
    entity: str
    value: str
    valid_from: datetime
    valid_to: datetime | None = None  # exclusive; None = still valid


@dataclass
class _Op:  # a CRDT replica operation
    id: str
    content: str
    agent_id: str
    workflow_id: str | None
    entity: str
    value: str
    ts: datetime
    vclock: dict[str, int] = field(default_factory=dict)


class FakeSUT(SUTAdapter):
    name = "fake"
    version = "0.1.0"
    capabilities = frozenset(
        {
            Capability.SCOPES,
            Capability.CONFLICTS,
            Capability.POLICIES,
            Capability.TEMPORAL,
            Capability.VECTOR_CLOCK,
        }
    )

    def setup(self) -> None:
        self._recs: list[_Rec] = []
        self._policy: dict[str | None, str] = {}
        self._events: list[dict] = []
        self._replicas: dict[str, list[_Op]] = {}
        self._tick = 0
        self._ids = itertools.count(1)

    def teardown(self) -> None:
        self.setup()

    # --- clock + ids --------------------------------------------------------
    def _now(self) -> datetime:
        t = _EPOCH + timedelta(seconds=self._tick)
        self._tick += 1
        return t

    def _new_id(self, prefix: str = "m") -> str:
        return f"{prefix}{next(self._ids)}"

    # --- core ops -----------------------------------------------------------
    def write(
        self, content, *, agent_id, scope="team", role=None, workflow_id=None
    ) -> WriteResult:
        entity, value = parse_entity(content)
        ts = self._now()
        # A SELF-update (same agent, same entity, new value) supersedes the
        # agent's own prior live record -> bitemporal history (S2). Cross-agent
        # disagreement is contention, not supersession; both stay live (S1/S6).
        for r in self._recs:
            if (
                r.valid_to is None
                and r.workflow_id == workflow_id
                and r.entity == entity
                and r.agent_id == agent_id
                and r.value != value
            ):
                r.valid_to = ts
        rec = _Rec(
            id=self._new_id(),
            content=content,
            agent_id=agent_id,
            role=role,
            scope=scope,
            workflow_id=workflow_id,
            created_at=ts,
            entity=entity,
            value=value,
            valid_from=ts,
        )
        self._recs.append(rec)
        return WriteResult(id=rec.id, created_at=ts, ok=True)

    def _visible(self, r: _Rec, agent_id: str, workflow_id: str | None) -> bool:
        if r.scope == "global":
            return True
        if r.workflow_id != workflow_id:
            return False  # team/private never cross workflows
        if r.scope == "team":
            return True
        if r.scope == "private":
            return r.agent_id == agent_id
        return False

    def _live_at(self, r: _Rec, at_time: datetime | None) -> bool:
        if at_time is None:
            return r.valid_to is None
        return r.valid_from <= at_time and (r.valid_to is None or at_time < r.valid_to)

    def search(
        self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None
    ) -> list[Hit]:
        q = query.strip().lower()
        cands = [
            r
            for r in self._recs
            if self._live_at(r, at_time)
            and self._visible(r, agent_id, workflow_id)
            and (q in r.entity or q in r.content.lower())
        ]
        # Resolve cross-agent contention per the active policy, per entity.
        policy = self._policy.get(workflow_id, "ignore")
        chosen: list[_Rec] = []
        by_entity: dict[str, list[_Rec]] = {}
        for r in cands:
            by_entity.setdefault(r.entity, []).append(r)
        for entity, group in by_entity.items():
            values = {r.value for r in group}
            if len(values) <= 1:
                chosen.extend(group)
                continue
            # genuine contention on this entity
            if policy == "ignore":
                chosen.extend(group)
            elif policy == "timestamp_wins":
                chosen.append(max(group, key=lambda r: r.created_at))
            elif policy == "planner_wins":
                planners = [r for r in group if r.role == "planner"]
                chosen.append(
                    max(planners or group, key=lambda r: r.created_at)
                )
            elif policy == "human_in_loop":
                self._emit_hitl(entity, group, workflow_id)
                chosen.extend(group)  # unresolved until a human acts
            else:
                chosen.extend(group)
        chosen.sort(key=lambda r: r.created_at, reverse=True)
        return [self._hit(r) for r in chosen[:top_k]]

    @staticmethod
    def _hit(r: _Rec) -> Hit:
        return Hit(
            id=r.id,
            content=r.content,
            agent_id=r.agent_id,
            scope=r.scope,
            created_at=r.created_at,
            role=r.role,
            score=1.0,
        )

    # --- conflicts + policy -------------------------------------------------
    def check_conflicts(self, content, *, agent_id, workflow_id=None) -> list[Conflict]:
        entity, value = parse_entity(content)
        out: list[Conflict] = []
        for r in self._recs:
            if (
                r.valid_to is None
                and r.workflow_id == workflow_id
                and r.entity == entity
                and r.value != value
            ):
                out.append(
                    Conflict(
                        entity=entity,
                        existing_id=r.id,
                        existing_content=r.content,
                        new_content=content,
                        existing_agent_id=r.agent_id,
                        existing_role=r.role,
                    )
                )
        return out

    def set_policy(self, policy, *, workflow_id=None) -> None:
        self._policy[workflow_id] = policy

    def _emit_hitl(self, entity, group, workflow_id) -> None:
        sig = ("hitl", workflow_id, entity, tuple(sorted(r.id for r in group)))
        if any(e.get("_sig") == sig for e in self._events):
            return
        self._events.append(
            {
                "_sig": sig,
                "type": "conflict.human_in_loop",
                "workflow_id": workflow_id,
                "entity": entity,
                "candidates": [
                    {"id": r.id, "content": r.content, "agent_id": r.agent_id}
                    for r in group
                ],
            }
        )

    def pending_events(self, *, workflow_id=None) -> list[dict]:
        return [
            {k: v for k, v in e.items() if k != "_sig"}
            for e in self._events
            if workflow_id is None or e.get("workflow_id") == workflow_id
        ]

    # --- CRDT / replica extension (S4) --------------------------------------
    def replica_write(
        self, replica, content, *, agent_id, workflow_id=None, vclock=None
    ) -> WriteResult:
        entity, value = parse_entity(content)
        ts = self._now()
        op = _Op(
            id=self._new_id("op"),
            content=content,
            agent_id=agent_id,
            workflow_id=workflow_id,
            entity=entity,
            value=value,
            ts=ts,
            vclock=dict(vclock or {}),
        )
        self._replicas.setdefault(replica, []).append(op)
        return WriteResult(id=op.id, created_at=ts, ok=True)

    def replica_sync(self, order) -> None:
        # Gossip: each (frm, to) step copies frm's ops missing from to. Repeating
        # the supplied order to a fixpoint guarantees full propagation regardless
        # of the (possibly reversed/partial) order given.
        for _ in range(len(order) + 2):
            for frm, to in order:
                have = {o.id for o in self._replicas.get(to, [])}
                for o in self._replicas.get(frm, []):
                    if o.id not in have:
                        self._replicas.setdefault(to, []).append(o)
                        have.add(o.id)

    def replica_state(self, replica, *, workflow_id=None) -> list[Hit]:
        ops = [
            o
            for o in self._replicas.get(replica, [])
            if workflow_id is None or o.workflow_id == workflow_id
        ]
        by_entity: dict[str, list[_Op]] = {}
        for o in ops:
            by_entity.setdefault(o.entity, []).append(o)
        out: list[Hit] = []
        for group in by_entity.values():
            # Deterministic winner across replicas: total order on
            # (ts, agent_id, op_id). This is what makes convergence order-independent.
            winner = max(group, key=lambda o: (o.ts, o.agent_id, o.id))
            out.append(
                Hit(
                    id=winner.id,
                    content=winner.content,
                    agent_id=winner.agent_id,
                    scope="team",
                    created_at=winner.ts,
                    score=1.0,
                )
            )
        out.sort(key=lambda h: h.id)
        return out

    def replica_history(self, *, workflow_id=None) -> list[str]:
        seen = set()
        for ops in self._replicas.values():
            for o in ops:
                if workflow_id is None or o.workflow_id == workflow_id:
                    seen.add(o.id)
        return sorted(seen)
