"""The SUTAdapter contract every system-under-test implements (DESIGN §5.1).

Adapters are black boxes over a public API. A scenario drives these methods and
asserts on outcomes. Methods an adapter can't support raise `Unsupported`; the
scenario then records `N/A` for the affected metric instead of a failure.

S4 (CRDT) needs a replica/vector-clock API most systems don't expose, so those
methods live here as optional extensions guarded by Capability.VECTOR_CLOCK.
"""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any

from .types import Conflict, Hit, WriteResult


class Unsupported(Exception):
    """Raised by an adapter method the SUT cannot perform. Caught by scenarios
    and recorded as N/A (not a failure)."""


class SUTAdapter(abc.ABC):
    name: str = "unnamed"
    version: str = "0.0.0"
    # Which Capability.* features this adapter supports. Scenarios consult this.
    capabilities: frozenset[str] = frozenset()
    # Whether per-op $ is measurable client-side. False for hosted services whose
    # cost is a server-side subscription (Mem0, AgentMem) — S7 then reports the
    # $ metrics as "not client-observable" rather than a misleading $0.
    cost_observable: bool = True

    # --- lifecycle ----------------------------------------------------------
    def setup(self) -> None:  # noqa: B027 - optional hook
        """Create connections / namespaces. Default no-op."""

    def teardown(self) -> None:  # noqa: B027 - optional hook
        """Clean up. Default no-op."""

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    # --- core memory ops ----------------------------------------------------
    @abc.abstractmethod
    def write(
        self,
        content: str,
        *,
        agent_id: str,
        scope: str = "team",
        role: str | None = None,
        workflow_id: str | None = None,
    ) -> WriteResult: ...

    @abc.abstractmethod
    def search(
        self,
        query: str,
        *,
        agent_id: str,
        workflow_id: str | None = None,
        top_k: int = 5,
        at_time: datetime | None = None,
    ) -> list[Hit]: ...

    # --- conflict / policy (optional) ---------------------------------------
    def check_conflicts(
        self, content: str, *, agent_id: str, workflow_id: str | None = None
    ) -> list[Conflict]:
        raise Unsupported(f"{self.name} does not support conflict detection")

    def set_policy(self, policy: str, *, workflow_id: str | None = None) -> None:
        raise Unsupported(f"{self.name} does not support conflict policies")

    def pending_events(self, *, workflow_id: str | None = None) -> list[dict[str, Any]]:
        """Events surfaced for human-in-the-loop resolution (S6). Default none."""
        raise Unsupported(f"{self.name} does not emit HITL events")

    # --- CRDT / replica extension (optional, S4) ----------------------------
    def replica_write(
        self,
        replica: str,
        content: str,
        *,
        agent_id: str,
        workflow_id: str | None = None,
        vclock: dict[str, int] | None = None,
    ) -> WriteResult:
        raise Unsupported(f"{self.name} has no replica/vector-clock API")

    def replica_sync(self, order: list[tuple[str, str]]) -> None:
        """Deliver writes between replicas in the given (from_replica, to_replica)
        order, simulating out-of-order/partitioned delivery."""
        raise Unsupported(f"{self.name} has no replica/vector-clock API")

    def replica_state(self, replica: str, *, workflow_id: str | None = None) -> list[Hit]:
        """The current resolved state visible on one replica."""
        raise Unsupported(f"{self.name} has no replica/vector-clock API")
