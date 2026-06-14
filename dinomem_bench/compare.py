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


def render(runs: list[dict], chosen, suts, provenance) -> str:
    cols = _sut_columns(suts)
    metrics = _ordered_metrics(chosen)
    # map scenario -> the (sut,scenario) chosen metrics for lookups
    lines: list[str] = []
    lines.append("# dinomem-bench — cross-system comparison")
    lines.append("")
    lines.append(f"Generated from {len(runs)} run(s) in `runs/`. Per (SUT, scenario) the most")
    lines.append("recent run with real metrics is used (provenance at the bottom). FakeSUT is")
    lines.append("the in-process reference, not a system under test.")
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
    if not runs_dir.exists():
        p.error(f"no runs directory at {runs_dir}")
    runs = _load_runs(runs_dir)
    if not runs:
        p.error(f"no runs found in {runs_dir}")
    chosen, suts, provenance = select(runs)
    md = render(runs, chosen, suts, provenance)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(f"✔ wrote {out}  ({len(runs)} runs, SUTs: {', '.join(_sut_columns(suts))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
