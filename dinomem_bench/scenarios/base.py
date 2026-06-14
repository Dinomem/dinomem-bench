"""Scenario framework: the MetricResult record + the Scenario base class.

A scenario is a deterministic script (setup -> operations -> assertions) that
emits one MetricResult per metric named in DESIGN §4. The runner gives each
scenario a freshly set-up SUT, captures timing, and writes the results to
runs/<id>/scenarios/<scenario>.jsonl.
"""

from __future__ import annotations

import abc
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from ..adapter import SUTAdapter

# metric status vocabulary
PASS = "pass"
FAIL = "fail"
NA = "na"        # SUT can't do what the metric needs (not a failure)
CRASH = "crash"  # SUT raised/timed out
INFO = "info"    # operational measurement, no pass/fail (S7)


@dataclass
class MetricResult:
    metric: str
    value: Any
    status: str
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def yn(b: bool) -> str:
    return "Y" if b else "N"


class Scenario(abc.ABC):
    id: str = "S?"
    slug: str = "scenario"
    version: str = "0.1.0"
    title: str = ""
    # capabilities the scenario needs; missing ones -> the dependent metrics N/A
    requires: frozenset[str] = frozenset()

    @abc.abstractmethod
    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        """Drive the SUT and return one MetricResult per metric."""

    # --- helpers scenarios use to build results -----------------------------
    @staticmethod
    def check(metric: str, ok: bool, *, value: Any = None, detail: str = "") -> MetricResult:
        return MetricResult(metric, yn(ok) if value is None else value, PASS if ok else FAIL, detail)

    @staticmethod
    def na(metric: str, reason: str) -> MetricResult:
        return MetricResult(metric, "N/A", NA, reason)

    @staticmethod
    def info(metric: str, value: Any, detail: str = "") -> MetricResult:
        return MetricResult(metric, value, INFO, detail)

    @staticmethod
    def settle(sut: SUTAdapter, *, query: str, agent_id: str, workflow_id, needle: str,
               timeout: float = 8.0) -> None:
        """Wait until `needle` is visible via search (lets an async-indexing SUT
        settle, and avoids hammering hosted backends with truly back-to-back
        conflicting writes). Returns immediately for in-process SUTs; bounded wait
        otherwise. Best-effort — never raises. `AMBENCH_SETTLE_TIMEOUT` overrides
        the cap for slow pipelines (e.g. Supermemory's ~30–60s indexing)."""
        timeout = float(os.environ.get("AMBENCH_SETTLE_TIMEOUT") or timeout)
        poll = float(os.environ.get("AMBENCH_SETTLE_POLL") or 2.0)
        deadline = time.time() + timeout
        needle = needle.lower()
        while time.time() < deadline:
            try:
                hits = sut.search(query, agent_id=agent_id, workflow_id=workflow_id)
            except Exception:
                hits = []
            if any(needle in h.content.lower() for h in hits):
                return
            time.sleep(poll)
