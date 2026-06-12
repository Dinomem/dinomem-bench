"""S7 — Operational metrics (cost + latency). DESIGN §4 S7.

A synthetic workload: 1,000 writes + 500 searches from a committed fixture.
Measures write/search latency percentiles and $/1k. (FakeSUT has no LLM/embeddings
so its $ is 0; real adapters report usd per op via OpTiming and this rolls it up.)
"""

from __future__ import annotations

import os
import time

from ..adapter import SUTAdapter
from ..fixtures import load_s7_writes
from .base import Scenario, MetricResult

WF = "s7-wf"
# DESIGN default is 1000 writes + 500 searches. Hosted SUTs with rate/quota limits
# (Mem0 free tier: 1k retrievals/mo; AgentMem: Gemini extraction quota) can scale
# down via env to get valid latency percentiles without burning the monthly quota.
N_WRITES = int(os.environ.get("AMBENCH_S7_WRITES", "1000"))
N_SEARCHES = int(os.environ.get("AMBENCH_S7_SEARCHES", "500"))


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    i = min(len(s) - 1, int(round((p / 100) * (len(s) - 1))))
    return s[i]


class S7Operational(Scenario):
    id = "S7"
    slug = "s7_operational"
    title = "Operational metrics (cost + latency)"
    requires = frozenset()

    def run(self, sut: SUTAdapter) -> list[MetricResult]:
        writes = load_s7_writes(N_WRITES)

        write_ms: list[float] = []
        write_usd = 0.0
        for w in writes:
            t0 = time.perf_counter()
            r = sut.write(w["content"], agent_id=w["agent_id"], scope=w.get("scope", "team"), workflow_id=WF)
            write_ms.append((time.perf_counter() - t0) * 1000)
            write_usd += getattr(r, "usd", 0.0) or 0.0

        search_ms: list[float] = []
        search_usd = 0.0
        for i in range(N_SEARCHES):
            q = writes[i % len(writes)]["query"]
            t0 = time.perf_counter()
            sut.search(q, agent_id="reader", workflow_id=WF, top_k=5)
            search_ms.append((time.perf_counter() - t0) * 1000)
            # adapters that incur per-search cost (e.g. embeddings) expose it here
            search_usd += float(getattr(sut, "last_search_usd", 0.0) or 0.0)

        observable = getattr(sut, "cost_observable", True)
        if not observable:
            note = "cost is a server-side subscription, not client-observable"
            wcost = scost = None  # don't report a misleading $0
        else:
            note = "no LLM/embedding cost" if (write_usd == 0 and search_usd == 0) else ""
            wcost = round((write_usd / max(1, len(writes))) * 1000, 4)
            scost = round((search_usd / max(1, N_SEARCHES)) * 1000, 4)
        return [
            self.info("Op.write_p50_ms", round(_pct(write_ms, 50), 3)),
            self.info("Op.write_p95_ms", round(_pct(write_ms, 95), 3)),
            self.info("Op.search_p50_ms", round(_pct(search_ms, 50), 3)),
            self.info("Op.search_p95_ms", round(_pct(search_ms, 95), 3)),
            self.info("Op.write_$_per_1k", "N/A" if wcost is None else wcost, detail=note),
            self.info("Op.search_$_per_1k", "N/A" if scost is None else scost, detail=note),
        ]
