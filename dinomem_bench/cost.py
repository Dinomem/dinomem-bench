"""Pre-flight cost estimator (DESIGN §6 budget cap).

Given the selected SUTs x scenarios, estimate the USD API spend of a run from
**operation counts x pinned model prices** (``dinomem_bench.models``) — never a
live API call. This lets ``--estimate-cost`` print a budget table and exit, and
lets a real run abort *before* any SUT work if the estimate exceeds ``--max-usd``.

Design notes:
  - **No SUT deps.** The per-SUT cost profile is a tiny table keyed by SUT name,
    declared here. Estimating ``pgvector`` never imports ``psycopg``/``openai``;
    estimating ``dinomem`` never imports ``httpx``. The estimate path is pure
    arithmetic over op-counts, so it works without any optional extra installed.
  - **In-process / hosted-flat-rate SUTs cost ~$0.** The FakeSUT makes no API
    calls; hosted services (mem0, zep, supermemory) bill a flat subscription, not
    per-op, so their per-run *marginal* API cost is $0 and a fake/hosted run never
    trips the budget. Only SUTs that call a metered per-token API we pay for
    directly (pgvector + langmem -> OpenAI embeddings; dinomem -> Gemini, billed
    server-side but priced here for the envelope) carry a non-zero estimate.
  - Token-per-op assumptions are deliberately conservative + fixed (determinism).

This module is stdlib-only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import models
from .models import EmbeddingModel, LLMModel

# --- per-op token assumptions ----------------------------------------------
# The benchmark's memories are short one-liners ("Deadline is Friday."). We bound
# each embedded op at a small fixed token count so the estimate is deterministic
# and an over- (never under-) estimate for the budget guard.
TOKENS_PER_WRITE_EMBED = 16
TOKENS_PER_SEARCH_EMBED = 16
# An extraction LLM pass over one write (input prompt + the memory; small output).
LLM_INPUT_TOKENS_PER_WRITE = 256
LLM_OUTPUT_TOKENS_PER_WRITE = 64


@dataclass(frozen=True)
class SUTCostProfile:
    """How a SUT spends money per memory op, for pre-flight estimation.

    Each field is optional: a SUT with no metered per-call API (FakeSUT, or a
    hosted flat-rate service) leaves them ``None`` and estimates to $0.

    ``metered`` is False for hosted flat-rate services whose API spend is a
    subscription, not per-op — their marginal run cost is $0 even if they embed
    server-side. ``write_extract_llm`` prices a per-write extraction/inference
    pass (cognee's cognify, DinoMem's Gemini extraction).
    """

    write_embed: EmbeddingModel | None = None
    search_embed: EmbeddingModel | None = None
    write_extract_llm: LLMModel | None = None
    metered: bool = True
    note: str = ""

    def write_usd(self) -> float:
        if not self.metered:
            return 0.0
        usd = 0.0
        if self.write_embed is not None:
            usd += (TOKENS_PER_WRITE_EMBED / 1000) * self.write_embed.usd_per_1k_tokens
        if self.write_extract_llm is not None:
            usd += (LLM_INPUT_TOKENS_PER_WRITE / 1000) * self.write_extract_llm.usd_per_1k_input_tokens
            usd += (LLM_OUTPUT_TOKENS_PER_WRITE / 1000) * self.write_extract_llm.usd_per_1k_output_tokens
        return usd

    def search_usd(self) -> float:
        if not self.metered or self.search_embed is None:
            return 0.0
        return (TOKENS_PER_SEARCH_EMBED / 1000) * self.search_embed.usd_per_1k_tokens


# A hosted-service flat-rate profile: cost is a subscription, not per-op metered.
_FLAT_RATE = SUTCostProfile(metered=False, note="hosted flat-rate subscription; $0 marginal per-op")
# A purely in-process / no-API profile (FakeSUT, the MinimalSUT stand-in).
_FREE = SUTCostProfile(metered=False, note="in-process, no API calls")

# name -> cost profile. Keyed by SUT name so estimation imports no SUT module.
# Adapters that don't call a metered per-token API estimate to $0.
SUT_COST_PROFILES: dict[str, SUTCostProfile] = {
    # in-process reference: no API spend at all.
    "fake": _FREE,
    # metered: we pay OpenAI per embedding token directly (write + search).
    "pgvector": SUTCostProfile(
        write_embed=models.OPENAI_EMBED_3_SMALL,
        search_embed=models.OPENAI_EMBED_3_SMALL,
        note="OpenAI text-embedding-3-small per write + search; no extraction",
    ),
    "langmem": SUTCostProfile(
        write_embed=models.OPENAI_EMBED_3_SMALL,
        search_embed=models.OPENAI_EMBED_3_SMALL,
        note="OpenAI embeddings via langgraph InMemoryStore index",
    ),
    # metered self-host graph: OpenAI embedding + an LLM extraction pass per write.
    "cognee": SUTCostProfile(
        write_embed=models.OPENAI_EMBED_3_SMALL,
        search_embed=models.OPENAI_EMBED_3_SMALL,
        write_extract_llm=models.OPENAI_GPT_4O_MINI,
        note="OpenAI embeddings + gpt-4o-mini cognify extraction per write",
    ),
    # DinoMem bills Gemini embeddings + extraction server-side. Not client-
    # observable, but priced here for the pre-flight envelope (metered=True so it
    # contributes to --max-usd; this is the spend the platform incurs on your behalf).
    "dinomem": SUTCostProfile(
        write_embed=models.GEMINI_EMBED_2,
        search_embed=models.GEMINI_EMBED_2,
        write_extract_llm=models.GEMINI_25_FLASH,
        note="Gemini embedding + 2.5-flash extraction (server-side, billed per usage)",
    ),
    # hosted flat-rate managed services: subscription cost, $0 marginal per-op.
    "mem0": _FLAT_RATE,
    "zep": _FLAT_RATE,
    "supermemory": _FLAT_RATE,
}


def cost_profile(sut_name: str) -> SUTCostProfile:
    """Cost profile for a SUT name; unknown SUTs default to free (no estimate)."""
    return SUT_COST_PROFILES.get(sut_name, _FREE)


# --- per-scenario op counts -------------------------------------------------
# Deterministic (write, search) counts each scenario drives against a SUT. These
# mirror the scenario scripts; auxiliary settle() polls are excluded (they return
# immediately for in-process SUTs and are best-effort, bounded, and free of writes).
# S5/S7 honour the same env scaling the scenarios use so the estimate tracks the
# actual planned run size.


def _s5_writes() -> int:
    return int(os.environ.get("AMBENCH_S5_WRITES", "50"))


def _s7_sizes() -> tuple[int, int]:
    return (
        int(os.environ.get("AMBENCH_S7_WRITES", "1000")),
        int(os.environ.get("AMBENCH_S7_SEARCHES", "500")),
    )


@dataclass(frozen=True)
class OpCounts:
    writes: int
    searches: int


def scenario_op_counts() -> dict[str, OpCounts]:
    """(scenario id -> OpCounts) for the deterministic ops each scenario issues.

    Counts are upper-ish bounds on metered calls: writes that embed, and explicit
    searches. check_conflicts is counted as one search-equivalent embed where a
    SUT detects conflicts. settle() polling reads are omitted (free / bounded)."""
    n5 = _s5_writes()
    w7, s7 = _s7_sizes()
    return {
        # S1: planner + executor writes (2); 1 check_conflicts (~search embed);
        # reads: resolved + 2 consistent readers (3 searches). +1 for the conflict embed.
        "S1": OpCounts(writes=2, searches=4),
        # S2: 2 writes; 2 at_time searches.
        "S2": OpCounts(writes=2, searches=2),
        # S3: private + team writes (2); isolated + team_visible + cross_workflow (3 searches).
        "S3": OpCounts(writes=2, searches=3),
        # S4: replica/CRDT only; in-process protocol, no metered API ops.
        "S4": OpCounts(writes=0, searches=0),
        # S5: 2 writes/iter * N iters; N token searches.
        "S5": OpCounts(writes=2 * n5, searches=n5),
        # S6: 4 policy sub-runs, each 2 writes + 1 read = 8 writes, 4 searches.
        "S6": OpCounts(writes=8, searches=4),
        # S7: the headline operational workload.
        "S7": OpCounts(writes=w7, searches=s7),
    }


# --- estimation -------------------------------------------------------------


@dataclass
class CellEstimate:
    sut: str
    scenario: str
    writes: int
    searches: int
    usd: float


@dataclass
class Estimate:
    cells: list[CellEstimate] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return sum(c.usd for c in self.cells)

    def by_sut(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for c in self.cells:
            out[c.sut] = out.get(c.sut, 0.0) + c.usd
        return out


def estimate(sut_names: list[str], scenario_ids: list[str]) -> Estimate:
    """Estimate run cost from op-counts x pinned prices. Pure arithmetic — imports
    no SUT module and needs no optional extra / network."""
    counts = scenario_op_counts()
    est = Estimate()
    for sut in sut_names:
        prof = cost_profile(sut)
        for sid in scenario_ids:
            oc = counts.get(sid, OpCounts(0, 0))
            usd = oc.writes * prof.write_usd() + oc.searches * prof.search_usd()
            est.cells.append(CellEstimate(sut, sid, oc.writes, oc.searches, usd))
    return est


def format_table(est: Estimate, max_usd: float) -> str:
    """Human-readable per-(sut, scenario) + per-sut + total USD table."""
    lines: list[str] = []
    lines.append(f"Pre-flight cost estimate (prices as of {models.PRICES_AS_OF}; "
                 f"op-counts x pinned model prices, not a live run)")
    lines.append("")
    header = f"{'SUT':<14} {'Scenario':<10} {'writes':>7} {'searches':>9} {'est USD':>12}"
    lines.append(header)
    lines.append("-" * len(header))
    for c in est.cells:
        lines.append(f"{c.sut:<14} {c.scenario:<10} {c.writes:>7} {c.searches:>9} {c.usd:>12.4f}")
    lines.append("-" * len(header))
    lines.append(f"{'per-SUT total':<14}")
    for sut, usd in est.by_sut().items():
        lines.append(f"{sut:<14} {'':<10} {'':>7} {'':>9} {usd:>12.4f}")
    lines.append("-" * len(header))
    lines.append(f"{'TOTAL':<14} {'':<10} {'':>7} {'':>9} {est.total_usd:>12.4f}")
    lines.append(f"(budget --max-usd {max_usd:.2f})")
    return "\n".join(lines)


def _fmt_usd(usd: float) -> str:
    """Show enough precision that a small-but-over estimate isn't printed as $0.00."""
    if usd == 0:
        return "0.00"
    if usd < 0.01:
        return f"{usd:.4f}"
    return f"{usd:.2f}"


def abort_message(est: Estimate, max_usd: float) -> str:
    """The message printed when an estimate exceeds the budget."""
    return (
        f"estimated ${_fmt_usd(est.total_usd)} exceeds --max-usd {max_usd:g}; "
        f"pass --max-usd to override or narrow --sut/--scenarios"
    )
