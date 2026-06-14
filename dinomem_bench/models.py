"""Pinned model registry + prices (DESIGN §6 reproducibility).

Every LLM / embedding model string any adapter uses is centralised here as a
**pinned** constant — no ``latest`` tags — together with a USD price, so the
pre-flight cost estimator (``dinomem_bench.cost``) can price a planned run from
operation counts alone, without a live API call.

This module is **stdlib-only** (the harness core has no runtime deps); it holds
constants + a couple of small dataclasses, nothing that imports a SUT's optional
deps. Adapters import the *string* constants from here so the pinned version and
the price never drift apart.

Prices are list prices in USD as of the pin date below; update both the model
string and its price together when re-pinning for a new quarterly run.
"""

from __future__ import annotations

from dataclasses import dataclass

# Date the prices below were last reconciled with published list prices.
PRICES_AS_OF = "2026-06-01"


@dataclass(frozen=True)
class EmbeddingModel:
    """A pinned embedding model + its token price.

    ``usd_per_1k_tokens`` is the embedding list price; ``dims`` is the output
    dimensionality the adapters index at.
    """

    name: str
    dims: int
    usd_per_1k_tokens: float


@dataclass(frozen=True)
class LLMModel:
    """A pinned LLM (extraction / judge) + its token prices."""

    name: str
    usd_per_1k_input_tokens: float
    usd_per_1k_output_tokens: float


# --- embedding models -------------------------------------------------------

# OpenAI text-embedding-3-small. Used by pgvector, langmem, and (via the cognee
# default) the cognee SUT. Pinned, no `latest`. $0.02 / 1M tokens = $2e-5 / 1k.
OPENAI_EMBED_3_SMALL = EmbeddingModel(
    name="text-embedding-3-small",
    dims=1536,
    usd_per_1k_tokens=0.00002,
)

# Google Gemini embedding (DinoMem's hosted embedding; dim 3072 per the core
# schema's vector(3072)). DinoMem bills this server-side, so it is not
# client-observable, but we still price it for the pre-flight estimate.
GEMINI_EMBED_2 = EmbeddingModel(
    name="gemini-embedding-2",
    dims=3072,
    usd_per_1k_tokens=0.00015,
)


# --- LLM models (extraction + judge) ----------------------------------------

# OpenAI gpt-4o-mini — extraction LLM for the self-host graph/floor SUTs that do
# inference (cognee's cognify; langmem/mem0 when infer is on). Pinned snapshot.
OPENAI_GPT_4O_MINI = LLMModel(
    name="gpt-4o-mini-2024-07-18",
    usd_per_1k_input_tokens=0.00015,
    usd_per_1k_output_tokens=0.0006,
)

# Google Gemini 2.5 Flash — DinoMem's extraction / conflict / rerank LLM
# (server-side, billed by the platform). Pinned, no `latest`.
GEMINI_25_FLASH = LLMModel(
    name="gemini-2.5-flash",
    usd_per_1k_input_tokens=0.0003,
    usd_per_1k_output_tokens=0.0025,
)

# Claude Sonnet — the LLM-as-judge (DESIGN §5.3), used sparingly. Pinned.
# Deterministic scenarios use no judge today, so this carries $0 weight in the
# current estimate, but the pin + price live here for when a judged scenario lands.
CLAUDE_SONNET_JUDGE = LLMModel(
    name="claude-sonnet-4-6",
    usd_per_1k_input_tokens=0.003,
    usd_per_1k_output_tokens=0.015,
)


__all__ = [
    "PRICES_AS_OF",
    "EmbeddingModel",
    "LLMModel",
    "OPENAI_EMBED_3_SMALL",
    "GEMINI_EMBED_2",
    "OPENAI_GPT_4O_MINI",
    "GEMINI_25_FLASH",
    "CLAUDE_SONNET_JUDGE",
]
