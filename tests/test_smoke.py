"""Smoke tests for the harness. Runs without third-party deps:
    python3 tests/test_smoke.py        # plain asserts
    python3 -m pytest                   # if pytest is installed
Validates two paths:
  1. FakeSUT (full capabilities) passes every correctness metric.
  2. A capability-less SUT records N/A for capability-gated metrics (not failures).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dinomem_bench.adapter import SUTAdapter
from dinomem_bench.scenarios import ALL
from dinomem_bench.scenarios.base import CRASH, FAIL, NA
from dinomem_bench.suts.fake import FakeSUT, parse_entity
from dinomem_bench.types import Hit, WriteResult


def _run(sut: SUTAdapter):
    results = {}
    for s in ALL:
        sut.setup()
        results[s.id] = s.run(sut)
        sut.teardown()
    return results


def test_fakesut_passes_all_correctness():
    res = _run(FakeSUT())
    for sid, metrics in res.items():
        for m in metrics:
            assert m.status != FAIL, f"{sid} {m.metric} failed: {m.detail}"
            assert m.status != CRASH, f"{sid} {m.metric} crashed: {m.detail}"


class MinimalSUT(SUTAdapter):
    """A bare store: write + substring search, NO capabilities. Stands in for a
    real system without conflicts/policies/temporal/CRDT support."""

    name = "minimal"
    version = "0.0.1"
    capabilities = frozenset()

    def setup(self):
        self._rows: list[dict] = []
        self._n = 0

    def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None):
        self._n += 1
        row = {"id": f"x{self._n}", "content": content, "agent_id": agent_id,
               "scope": scope, "wf": workflow_id, "ts": datetime(2026, 1, 1)}
        self._rows.append(row)
        return WriteResult(id=row["id"], created_at=row["ts"])

    def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None):
        q = query.lower()
        return [
            Hit(id=r["id"], content=r["content"], agent_id=r["agent_id"], scope=r["scope"],
                created_at=r["ts"])
            for r in self._rows
            if r["wf"] == workflow_id and q in r["content"].lower()
        ][:top_k]


def test_minimal_sut_records_na_not_fail():
    res = _run(MinimalSUT())
    # capability-gated metrics must be N/A, never a hard failure
    na_metrics = {m.metric for m in res["S2"] + res["S4"] if m.status == NA}
    assert "T1.t0" in na_metrics and "T1.t1" in na_metrics, res["S2"]
    assert any(m.status == NA for m in res["S4"]), res["S4"]
    # S7 (no capability requirement) still produces operational numbers
    assert any(m.metric.startswith("Op.") for m in res["S7"])
    # nothing should crash
    for sid, metrics in res.items():
        for m in metrics:
            assert m.status != CRASH, f"{sid} {m.metric} crashed: {m.detail}"


def test_parse_entity():
    assert parse_entity("Deadline is Friday.") == ("deadline", "friday")
    assert parse_entity("Owner is Bob") == ("owner", "bob")
    e, v = parse_entity("just a sentence")
    assert e == v == "just a sentence"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
