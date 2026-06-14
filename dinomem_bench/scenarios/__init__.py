"""Scenario registry, in canonical S1..S7 order."""

from __future__ import annotations

from .base import Scenario
from .s1_contradictory import S1Contradictory
from .s2_temporal import S2Temporal
from .s3_scope import S3Scope
from .s4_crdt import S4Crdt
from .s5_isolation import S5Isolation
from .s6_policy import S6Policy
from .s7_operational import S7Operational

ALL: list[Scenario] = [
    S1Contradictory(),
    S2Temporal(),
    S3Scope(),
    S4Crdt(),
    S5Isolation(),
    S6Policy(),
    S7Operational(),
]

_BY_KEY = {}
for _s in ALL:
    _BY_KEY[_s.id.lower()] = _s   # "s1"
    _BY_KEY[_s.slug] = _s         # "s1_contradictory"


def select(spec: str) -> list[Scenario]:
    """spec is 'all' or a comma list of ids/slugs, e.g. 's1,s4' or 's1_contradictory'."""
    if spec.strip().lower() == "all":
        return list(ALL)
    out: list[Scenario] = []
    for part in spec.split(","):
        key = part.strip().lower()
        if not key:
            continue
        if key not in _BY_KEY:
            raise KeyError(f"unknown scenario '{part}'. Known: {', '.join(s.id for s in ALL)}")
        s = _BY_KEY[key]
        if s not in out:
            out.append(s)
    return out
