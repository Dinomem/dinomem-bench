"""SUT adapter registry. Real systems register a lazy factory here so importing
this module never pulls a system's optional deps until that SUT is selected."""

from __future__ import annotations

from collections.abc import Callable

from ..adapter import SUTAdapter


def _make_fake() -> SUTAdapter:
    from .fake import FakeSUT

    return FakeSUT()


def _make_pgvector() -> SUTAdapter:
    from .pgvector import PgvectorSUT

    return PgvectorSUT()


def _make_agentmem() -> SUTAdapter:
    from .agentmem import AgentMemSUT

    return AgentMemSUT()


# name -> zero-arg factory (lazy import inside).
REGISTRY: dict[str, Callable[[], SUTAdapter]] = {
    "fake": _make_fake,
    "pgvector": _make_pgvector,
    "agentmem": _make_agentmem,
}


def make(name: str) -> SUTAdapter:
    if name not in REGISTRY:
        raise KeyError(f"unknown SUT '{name}'. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[name]()


def available() -> list[str]:
    return sorted(REGISTRY)
