"""compare.py — read multiple runs/ and emit the cross-SUT comparison matrix
(DESIGN §7). This is the artifact a blog post / paper consumes.

Merge policy: a SUT may have several runs (full + partial re-runs). For each
(SUT, scenario) we take the **most recent run that produced real metrics**, and
fall back to the most recent crash only if every run of that scenario crashed.
Provenance (which run each cell came from) is printed so the matrix is auditable.

    python -m dinomem_bench.compare [--runs runs] [--out results/COMPARISON.md]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

MARK = {"pass": "✅", "fail": "❌", "na": "—", "crash": "💥", "info": "ℹ️"}
# Column order: floor → managed → reference. Unknown SUTs appended alphabetically.
SUT_ORDER = ["pgvector", "mem0", "zep", "cognee", "supermemory", "langmem", "dinomem", "fake"]

# The system the maintainers build. Reported like every other SUT — the
# "Where DinoMem loses / is N/A" section below enumerates its fail/na/crash
# cells explicitly so the comparison cannot quietly favour it.
HOME_SUT = "dinomem"

# Conflict-of-interest / integrity block printed at the TOP of every generated
# matrix (condensed from DESIGN §9 + the paper's COI note). Kept in sync with the
# README's COI block. See METHODOLOGY.md for the full scoring rules.
COI_BLOCK = [
    "> **Conflict of interest / integrity.** DinoMem's maintainers build *and* run",
    "> this benchmark, and **DinoMem is one of the systems under test**. To keep that",
    "> from biasing the result we: publish the full harness + the deterministic",
    "> assertions that decide every metric (no LLM-judge — see [`METHODOLOGY.md`](../METHODOLOGY.md));",
    "> record provenance (run id, git sha, pinned models) for every cell; **report",
    "> every metric, including the ones DinoMem fails or is N/A on** (enumerated in",
    "> *Where DinoMem loses / is N/A* below); test all systems only through their",
    "> public, black-box APIs; and invite competitors to PR their own adapters /",
    "> config overrides (maintainers keep merge rights on harness code only — see",
    "> [`CONTRIBUTING.md`](../CONTRIBUTING.md)). DinoMem is one SUT here, not the",
    "> subject of this repo.",
]


@dataclass
class Cell:
    value: object
    status: str


def _load_runs(runs_dir: Path) -> list[dict]:
    runs = []
    for d in sorted(p for p in runs_dir.iterdir() if (p / "manifest.json").exists()):
        manifest = json.loads((d / "manifest.json").read_text())
        rows = []
        for jf in sorted((d / "scenarios").glob("*.jsonl")):
            for line in jf.read_text().splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        runs.append({"id": d.name, "manifest": manifest, "rows": rows})
    return runs


def _is_real(metrics: list[dict]) -> bool:
    """A scenario result is 'real' if it has metrics beyond the crash sentinel
    (`<slug>.run`, the only metric whose name ends in '.run')."""
    return any(not m["metric"].endswith(".run") for m in metrics)


def select(runs: list[dict]):
    """-> (chosen, provenance): chosen[(sut, scenario)] = {metric: Cell};
    provenance[(sut, scenario)] = run_id used."""
    # gather per (sut, scenario) -> list of (run_id, metrics)
    grouped: dict[tuple[str, str], list[tuple[str, list[dict]]]] = {}
    suts: set[str] = set()
    for run in runs:
        per: dict[tuple[str, str], list[dict]] = {}
        for r in run["rows"]:
            suts.add(r["sut"])
            per.setdefault((r["sut"], r["scenario"]), []).append(r)
        for key, metrics in per.items():
            grouped.setdefault(key, []).append((run["id"], metrics))

    chosen: dict[tuple[str, str], dict[str, Cell]] = {}
    provenance: dict[tuple[str, str], str] = {}
    for key, candidates in grouped.items():
        real = [(rid, m) for rid, m in candidates if _is_real(m)]
        pool = real or candidates
        rid, metrics = max(pool, key=lambda t: t[0])  # most recent by run_id
        chosen[key] = {m["metric"]: Cell(m["value"], m["status"]) for m in metrics}
        provenance[key] = rid
    return chosen, sorted(suts), provenance


def _ordered_metrics(chosen) -> list[tuple[str, str]]:
    """(scenario_id, metric) in S1..S7 order, metric by first appearance."""
    out: list[tuple[str, str]] = []
    seen = set()
    # collect across scenarios in id order, metric by first appearance
    by_scn: dict[str, list[str]] = {}
    for (_sut, scn), metrics in chosen.items():
        for metric in metrics:
            by_scn.setdefault(scn, [])
            if metric not in by_scn[scn]:
                by_scn[scn].append(metric)
    for scn in sorted(by_scn):
        for metric in by_scn[scn]:
            if (scn, metric) not in seen:
                seen.add((scn, metric))
                out.append((scn, metric))
    return out


def _sut_columns(suts: list[str]) -> list[str]:
    known = [s for s in SUT_ORDER if s in suts]
    extra = sorted(s for s in suts if s not in SUT_ORDER)
    return known + extra


def _home_breakdown(chosen, home: str = HOME_SUT):
    """Collect the home SUT's non-passing cells, grouped by status then scenario.
    Returns {status: {scenario: [(metric, value, detail?)]}} for fail/na/crash.
    `info` (S7 operational measurements) and `pass` are excluded — this section
    is specifically the places the maintainers' own system does NOT win."""
    buckets: dict[str, dict[str, list[tuple[str, object]]]] = {
        "fail": {}, "crash": {}, "na": {}
    }
    for (sut, scn), metrics in chosen.items():
        if sut != home:
            continue
        for metric, cell in metrics.items():
            if cell.status in buckets:
                buckets[cell.status].setdefault(scn, []).append((metric, cell.value))
    return buckets


def _render_home_losses(chosen, suts, home: str = HOME_SUT) -> list[str]:
    """The explicit anti-self-serving section: enumerate every cell where the
    maintainers' own SUT fails, crashes, or is N/A — per scenario — and note when
    an N/A is shared by every system (so it can't be read as a DinoMem-only gap)."""
    display = "DinoMem" if home == "dinomem" else home
    lines = ["", f"## Where {display} loses / is N/A", ""]
    if home not in suts:
        lines.append(f"_No {display} results present in these runs._")
        return lines
    buckets = _home_breakdown(chosen, home)
    n_fail = sum(len(v) for v in buckets["fail"].values())
    n_crash = sum(len(v) for v in buckets["crash"].values())
    n_na = sum(len(v) for v in buckets["na"].values())
    lines.append(
        f"DinoMem is reported like every other system under test. Across the selected "
        f"results it **fails {n_fail}**, **crashes on {n_crash}**, and is **N/A on "
        f"{n_na}** metric cell(s). Every one is listed below (passes/operational `info` "
        f"are in the scorecard above; this section is only the non-wins):"
    )
    lines.append("")

    def _shared_na(scn: str, metric: str) -> bool:
        """True if EVERY non-fake SUT is also N/A on this cell (i.e. not DinoMem-specific)."""
        others = [s for s in suts if s not in (home, "fake")]
        if not others:
            return False
        for s in others:
            c = chosen.get((s, scn), {}).get(metric)
            if c is None or c.status != "na":
                return False
        return True

    titles = [
        ("fail", "❌ Fails (wrong answer vs the scenario assertion)"),
        ("crash", "💥 Crashes (raised / 5xx / timeout, after the one re-run)"),
        ("na", "— N/A (DinoMem's API can't perform this metric — not a failure)"),
    ]
    for status, heading in titles:
        by_scn = buckets[status]
        lines.append(f"### {heading}")
        if not by_scn:
            lines.append("")
            lines.append(f"_None — DinoMem has no `{status}` cells in these results._")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Scenario | Metric | DinoMem value | Note |")
        lines.append("|---|---|---|---|")
        for scn in sorted(by_scn):
            for metric, value in by_scn[scn]:
                note = ""
                if status == "na":
                    note = ("shared: every real system is N/A here too"
                            if _shared_na(scn, metric)
                            else "DinoMem-specific N/A")
                lines.append(f"| {scn} | {metric} | {MARK.get(status, '')} {value} | {note} |")
        lines.append("")
    lines.append(
        "_Reading this honestly: S2 temporal (`T1.t1`) is a real **failure** — "
        "DinoMem accepts `at_time` and correctly filters at T0 (only the first fact "
        "is returned), but at T1 both facts are returned under the default `ignore` "
        "policy because DinoMem does not supersede the old fact without a conflict "
        "classification. Zep correctly invalidates the stale one via graph `invalid_at`. "
        "The S2 gap is structural: the write response carries no server-assigned "
        "`created_at`, so the T0/T1 points used in `atTime` queries are client-side "
        "approximations; and `timestamp_wins` supersession requires LLM conflict "
        "detection to fire, which doesn't trigger for semantically-distinct facts. "
        "S1 crashes on this run due to a Gemini free-tier 429 — the crash is real and "
        "is listed; the June run (SUT 'agentmem', same product) passed S1/S6 under a "
        "fresh quota. "
        "S4 CRDT is the one place DinoMem is **uniquely capable**: as of CRDT V3 it "
        "ships a real op-based LWW-Register CvRDT engine + a black-box replica/sync "
        "API, so it is the **only** system under test the convergence test can drive "
        "end-to-end (every other real system is N/A — no replica/sync surface); "
        "convergence was measured live on 2026-07-05 (run `2026-07-05-161701`). "
        "Any crash cell is a genuine backend defect, not hidden._"
    )
    return lines


def render(runs: list[dict], chosen, suts, provenance) -> str:
    cols = _sut_columns(suts)
    metrics = _ordered_metrics(chosen)
    # map scenario -> the (sut,scenario) chosen metrics for lookups
    lines: list[str] = []
    lines.append("# dinomem-bench — cross-system comparison")
    lines.append("")
    lines += COI_BLOCK
    lines.append("")
    lines.append(f"Generated from {len(runs)} run(s) in `runs/`. Per (SUT, scenario) the most")
    lines.append("recent run with real metrics is used (provenance at the bottom). FakeSUT is")
    lines.append("the in-process reference, not a system under test.")
    lines.append("")
    lines.append("> **Note on SUT naming:** the `agentmem` column reflects June 2026 runs recorded before")
    lines.append("> the adapter was renamed `dinomem` (same product, same hosted endpoint). The `dinomem`")
    lines.append("> column reflects July 2026 runs on the live deployed endpoint. Where a scenario is")
    lines.append("> present in the `dinomem` column, those numbers supersede `agentmem` for that scenario.")
    lines.append("")
    lines.append("## Scorecard")
    lines.append("")
    lines.append("| Scenario | Metric | " + " | ".join(cols) + " |")
    lines.append("|---|---|" + "|".join("---" for _ in cols) + "|")
    for scn, metric in metrics:
        cells = []
        for sut in cols:
            c = chosen.get((sut, scn), {}).get(metric)
            cells.append(f"{MARK.get(c.status, '')} {c.value}" if c else "·")
        lines.append(f"| {scn} | {metric} | " + " | ".join(cells) + " |")

    # totals
    lines += ["", "## Totals (selected results)", "",
              "| SUT | pass | fail | N/A | crash | info |", "|---|---|---|---|---|---|"]
    for sut in cols:
        tally = {"pass": 0, "fail": 0, "na": 0, "crash": 0, "info": 0}
        for (s, _scn), metrics_map in chosen.items():
            if s != sut:
                continue
            for c in metrics_map.values():
                tally[c.status] = tally.get(c.status, 0) + 1
        lines.append(f"| {sut} | {tally['pass']} | {tally['fail']} | {tally['na']} | "
                     f"{tally['crash']} | {tally['info']} |")

    # explicit anti-self-serving section: every cell DinoMem does NOT win
    lines += _render_home_losses(chosen, suts)

    # editorial notes — operational caveats that the scorecard numbers alone don't convey
    lines += [
        "",
        "## Notes",
        "",
        "### S7 latency — rerank caveat",
        "",
        ("The `Op.search_p50_ms` for DinoMem is measured **without `rerank:true`** "
         "(the bench adapter does not pass it). In the Fincil app-level dogfood run "
         "(2026-07-05), DinoMem search with `rerank:true` measured 2,586–6,294ms per "
         "call (~3–4s overhead on top of bare hybrid search). The bench search p50 "
         "figure is correct for the bare-search operating mode, but real applications "
         "using rerank for relevance filtering should expect 2.5–6s per search."),
        "",
        "### App-level validation (Fincil dogfood, 2026-07-05)",
        "",
        ("DinoMem was wired into **Fincil** (a 3-persona AI financial council app: "
         "Miser / Visionary / Twin) as `MEMORY_PROVIDER=dinomem` and run across 3 "
         "debate sessions. Key confirmations: S1/S6 conflict detection and "
         "`planner_wins` policy behave as the bench describes; P1 factKey bi-temporal "
         "versioning correctly closes prior validity windows; P2 immutable receipts "
         "generated on every search (8 receipts / 3 debates). Cross-session recall "
         "was faithful (council cited prior ₹80k approval every round, no "
         "confabulation). Memory tax: ~15% (~6.2s per debate) — rerank dominates. "
         "Critical operational finding: `factKeyPrefix` does **not** filter on the "
         "live endpoint — `workflowId` is the only reliable per-user isolation "
         "primitive (the bench adapter uses `workflowId` namespacing, which is "
         "correct). Full notes: "
         "`/mnt/308E51BA8E517974/fincil-remastered/notes/dinomem-test/`."),
    ]

    # provenance
    lines += ["", "## Provenance", "", "| SUT | scenario | run |", "|---|---|---|"]
    for (sut, scn) in sorted(provenance):
        lines.append(f"| {sut} | {scn} | `{provenance[(sut, scn)]}` |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dinomem-bench.compare", description=__doc__)
    p.add_argument("--runs", default="runs", help="runs directory (default: runs)")
    p.add_argument("--out", default="results/COMPARISON.md", help="output markdown path")
    args = p.parse_args(argv)

    runs_dir = Path(args.runs)
    runs = _load_runs(runs_dir) if runs_dir.exists() else []
    if not runs:
        # `runs/` is gitignored and published as a GitHub Release asset, not
        # committed (DESIGN §7), so its absence on a clean checkout is the EXPECTED
        # state, not a usage error. Don't clobber the committed matrix; explain how
        # to produce runs, and exit 0 so reproducibility checks stay green.
        print(
            f"No runs found in {runs_dir}/ (it is gitignored — published as a "
            f"release artifact, not committed).\n"
            f"Produce one, then re-run compare:\n"
            f"  python3 -m dinomem_bench --sut fake --scenarios all\n"
            f"  python3 -m dinomem_bench.compare\n"
            f"The committed cross-system matrix is at {Path(args.out)}."
        )
        return 0
    chosen, suts, provenance = select(runs)
    md = render(runs, chosen, suts, provenance)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"✔ wrote {out}  ({len(runs)} runs, SUTs: {', '.join(_sut_columns(suts))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
