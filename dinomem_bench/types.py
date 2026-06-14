"""Shared types for the harness: scopes, policies, capabilities, and the
result objects adapters return. Kept dependency-free so any adapter can import it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# --- vocabularies -----------------------------------------------------------

# Visibility scopes a write can carry (DESIGN §2 / S3).
SCOPES = ("private", "team", "global")

# Conflict-resolution policies (DESIGN §2 / S6). Semantics:
#   ignore         — keep all writes; no resolution; read returns all.
#   timestamp_wins — most recent write wins on read.
#   planner_wins   — the 'planner' role's write wins on read.
#   human_in_loop  — surface an event; leave unresolved (read returns all) until
#                    a human resolves. We score whether the event is emitted.
POLICIES = ("ignore", "timestamp_wins", "planner_wins", "human_in_loop")


class Capability:
    """Feature flags an adapter advertises. Scenarios that need a capability the
    SUT lacks record `N/A` rather than a failure (DESIGN §5.4)."""

    SCOPES = "scopes"            # private/team/global visibility enforcement
    CONFLICTS = "conflicts"      # check_conflicts() surfaces contradictions
    POLICIES = "policies"        # set_policy() + policy-aware reads
    TEMPORAL = "temporal"        # at_time= bitemporal queries (S2)
    VECTOR_CLOCK = "vector_clock"  # replica/CRDT API for S4


# --- result objects ---------------------------------------------------------


@dataclass
class WriteResult:
    """Returned by SUTAdapter.write(). `created_at` is the timestamp the SUT
    assigned to the write — scenarios use it for temporal queries (S2) instead
    of relying on wall-clock sleeps."""

    id: str
    created_at: datetime
    ok: bool = True
    usd: float = 0.0  # cost of this write (extraction + embedding), for S7
    raw: Any = None  # raw SUT response, for audit


@dataclass
class Hit:
    """A single search result."""

    id: str
    content: str
    agent_id: str
    scope: str
    created_at: datetime
    score: float = 0.0
    role: str | None = None
    raw: Any = None


@dataclass
class Conflict:
    """A contradiction surfaced by check_conflicts(): an existing memory whose
    value disagrees with the candidate `new_content` about the same entity."""

    entity: str
    existing_id: str
    existing_content: str
    new_content: str
    existing_agent_id: str | None = None
    existing_role: str | None = None


@dataclass
class OpTiming:
    """One operation's latency sample, for S7 histograms."""

    op: str  # "write" | "search"
    ms: float
    usd: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)
