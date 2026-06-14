"""Generate the paper figures from committed runs.

  python paper/make_figures.py            # -> paper/figures/{capability_heatmap,latency}.png|pdf

Reuses dinomem_bench.compare for the same merge/provenance logic as the matrix,
so figures and table never disagree. Requires matplotlib.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dinomem_bench import compare  # noqa: E402

SUT_ORDER = ["pgvector", "langmem", "mem0", "supermemory", "cognee", "zep", "dinomem"]
# Correctness metrics in display order (S7 latency handled separately).
METRIC_ROWS = [
    ("S1", "C1.detected", "S1 detect"),
    ("S1", "C1.resolved", "S1 resolve"),
    ("S2", "T1.t0", "S2 @T0"),
    ("S2", "T1.t1", "S2 @T1"),
    ("S3", "S3.isolated", "S3 isolated"),
    ("S3", "S3.team_visible", "S3 team-vis"),
    ("S3", "S3.cross_workflow", "S3 cross-wf"),
    ("S4", "S4.converge", "S4 converge"),
    ("S4", "S4.deterministic", "S4 determ."),
    ("S5", "S5.leakage_rate", "S5 no-leak"),
    ("S6", "P.planner_wins.correct", "S6 planner"),
    ("S6", "P.timestamp_wins.correct", "S6 timestamp"),
    ("S6", "P.human_in_loop.surfaced", "S6 HITL"),
]
STATUS_COLOR = {"pass": "#1a9850", "fail": "#d73027", "na": "#cfd3d6", "crash": "#7b3294", "info": "#4575b4"}


def load():
    runs = compare._load_runs(ROOT / "runs")
    chosen, suts, _prov = compare.select(runs)
    suts = [s for s in SUT_ORDER if s in suts]
    return chosen, suts


def heatmap(chosen, suts, out):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(1.1 * len(suts) + 2.2, 0.42 * len(METRIC_ROWS) + 1.2))
    for r, (scn, metric, _label) in enumerate(METRIC_ROWS):
        for c, sut in enumerate(suts):
            cell = chosen.get((sut, scn), {}).get(metric)
            color = STATUS_COLOR.get(cell.status, "#ffffff") if cell else "#ffffff"
            ax.add_patch(plt.Rectangle((c, r), 1, 1, facecolor=color, edgecolor="white", linewidth=1.5))
            if cell and cell.status in ("pass", "fail"):
                ax.text(c + 0.5, r + 0.5, "✓" if cell.status == "pass" else "✗",
                        ha="center", va="center", color="white", fontsize=11, fontweight="bold")
    ax.set_xlim(0, len(suts)); ax.set_ylim(0, len(METRIC_ROWS)); ax.invert_yaxis()
    ax.set_xticks([c + 0.5 for c in range(len(suts))]); ax.set_xticklabels(suts, rotation=30, ha="right", fontsize=9)
    ax.set_yticks([r + 0.5 for r in range(len(METRIC_ROWS))]); ax.set_yticklabels([m[2] for m in METRIC_ROWS], fontsize=9)
    ax.set_xticks(range(len(suts) + 1), minor=True); ax.tick_params(length=0)
    ax.set_title("Multi-agent memory capability matrix (dinomem-bench S1–S6)", fontsize=11, pad=10)
    legend = [Patch(facecolor=STATUS_COLOR["pass"], label="pass"),
              Patch(facecolor=STATUS_COLOR["fail"], label="fail"),
              Patch(facecolor=STATUS_COLOR["na"], label="N/A (no API)")]
    ax.legend(handles=legend, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=9)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out.with_suffix("." + ext), dpi=200, bbox_inches="tight")
    plt.close(fig)


def latency(chosen, suts, out):
    import matplotlib.pyplot as plt
    import numpy as np

    def val(sut, metric):
        c = chosen.get((sut, "S7"), {}).get(metric)
        try:
            return float(c.value) if c else None
        except (TypeError, ValueError):
            return None

    labels, wp50, sp50 = [], [], []
    for sut in suts:
        w, s = val(sut, "Op.write_p50_ms"), val(sut, "Op.search_p50_ms")
        if w is None and s is None:
            continue
        labels.append(sut); wp50.append(w or 0.1); sp50.append(s or 0.1)
    x = np.arange(len(labels)); width = 0.4
    fig, ax = plt.subplots(figsize=(1.1 * len(labels) + 2, 4.2))
    ax.bar(x - width / 2, wp50, width, label="write p50", color="#4575b4")
    ax.bar(x + width / 2, sp50, width, label="search p50", color="#91bfdb")
    ax.set_yscale("log"); ax.set_ylabel("latency p50 (ms, log scale)")
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9)
    ax.set_title("Per-operation latency (S7), log scale", fontsize=11)
    ax.legend(frameon=False); ax.grid(axis="y", which="both", alpha=0.3)
    for xi, v in zip(x - width / 2, wp50):
        ax.text(xi, v * 1.1, f"{v:.0f}", ha="center", va="bottom", fontsize=7)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out.with_suffix("." + ext), dpi=200, bbox_inches="tight")
    plt.close(fig)


def main():
    out_dir = ROOT / "paper" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen, suts = load()
    heatmap(chosen, suts, out_dir / "capability_heatmap")
    latency(chosen, suts, out_dir / "latency")
    print(f"✔ wrote figures to {out_dir} for SUTs: {', '.join(suts)}")


if __name__ == "__main__":
    main()
