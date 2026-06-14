"""Committed fixture data for deterministic runs (DESIGN §6).

The S7 workload lives in fixtures/s7_writes.jsonl so any run uses identical
inputs. If the file is missing it is generated deterministically and written,
so the first run materialises a committable fixture.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
_S7_PATH = _FIXTURE_DIR / "s7_writes.jsonl"

_AGENTS = ["planner", "executor", "researcher", "critic"]
_ENTITIES = [
    "deadline", "budget", "owner", "status", "priority", "venue", "headcount",
    "vendor", "region", "channel", "milestone", "risk", "scope", "sla", "tier",
]
_VALUES = [
    "friday", "monday", "q3", "approved", "high", "low", "alice", "bob", "green",
    "red", "blocked", "shipped", "12000", "us-east", "tier-1", "pending",
]


def generate_s7_writes(n: int = 1000, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n):
        entity = f"{rng.choice(_ENTITIES)}-{i % 200}"  # 200 distinct entities, reused
        value = rng.choice(_VALUES)
        rows.append(
            {
                "content": f"{entity} is {value}.",
                "agent_id": rng.choice(_AGENTS),
                "scope": "team",
                "query": entity,
            }
        )
    return rows


def load_s7_writes(n: int = 1000) -> list[dict]:
    if _S7_PATH.exists():
        rows = [json.loads(line) for line in _S7_PATH.read_text().splitlines() if line.strip()]
        if len(rows) >= n:
            return rows[:n]
    rows = generate_s7_writes(n)
    write_s7_fixture(rows)
    return rows


def write_s7_fixture(rows: list[dict]) -> Path:
    _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _S7_PATH.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return _S7_PATH
