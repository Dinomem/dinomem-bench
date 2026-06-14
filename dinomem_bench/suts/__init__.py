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


def _make_dinomem() -> SUTAdapter:
    from .dinomem import DinoMemSUT

    return DinoMemSUT()


def _make_mem0() -> SUTAdapter:
    from .mem0 import Mem0SUT

    return Mem0SUT()


def _make_supermemory() -> SUTAdapter:
    from .supermemory import SupermemorySUT

    return SupermemorySUT()


def _make_zep() -> SUTAdapter:
    from .zep import ZepSUT

    return ZepSUT()


def _make_langmem() -> SUTAdapter:
    from .langmem import LangMemSUT

    return LangMemSUT()


def _make_cognee() -> SUTAdapter:
    from .cognee_sut import CogneeSUT

    return CogneeSUT()


# name -> zero-arg factory (lazy import inside).
REGISTRY: dict[str, Callable[[], SUTAdapter]] = {
    "fake": _make_fake,
    "pgvector": _make_pgvector,
    "dinomem": _make_dinomem,
    "mem0": _make_mem0,
    "supermemory": _make_supermemory,
    "zep": _make_zep,
    "langmem": _make_langmem,
    "cognee": _make_cognee,
}


def make(name: str) -> SUTAdapter:
    if name not in REGISTRY:
        raise KeyError(f"unknown SUT '{name}'. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[name]()


def available() -> list[str]:
    return sorted(REGISTRY)
