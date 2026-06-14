"""The run loop + output format (DESIGN §7).

Produces a self-contained runs/<run_id>/ directory:
    manifest.json   run id, time, sut versions+capabilities, scenarios, env
    scenarios/<slug>.jsonl   one line per metric per sut
    timing.json     per-sut per-scenario wall time
    cost.json       per-sut per-scenario USD (from S7 $ metrics)
    summary.md      human-readable matrix (auto-generated)
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .adapter import SUTAdapter
from .scenarios.base import CRASH, MetricResult, Scenario
from .suts import make as make_sut


def _git_sha() -> str | None:
    try:
        here = Path(__file__).resolve().parent
        out = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")


@dataclass
class ScenarioRun:
    sut: str
    scenario: str
    scenario_id: str
    version: str
    wall_ms: float
    metrics: list[MetricResult]


def _run_scenario(sut: SUTAdapter, scenario: Scenario) -> tuple[list[MetricResult], float]:
    """Run one scenario against a fresh SUT state. On exception, re-run once
    (DESIGN §5.4) before recording a crash."""
    for attempt in (1, 2):
        sut.setup()
        t0 = time.perf_counter()
        try:
            metrics = scenario.run(sut)
            wall = (time.perf_counter() - t0) * 1000
            return metrics, wall
        except Exception:
            wall = (time.perf_counter() - t0) * 1000
            if attempt == 2:
                tb = traceback.format_exc().strip().splitlines()[-1]
                return [MetricResult(f"{scenario.slug}.run", "crash", CRASH, tb)], wall
        finally:
            try:
                sut.teardown()
            except Exception:
                pass
    return [], 0.0  # unreachable


def run(sut_names: list[str], scenarios: list[Scenario], out_root: Path) -> Path:
    run_dir = out_root / _run_id()
    (run_dir / "scenarios").mkdir(parents=True, exist_ok=True)

    runs: list[ScenarioRun] = []
    sut_meta: list[dict] = []

    for sut_name in sut_names:
        sut = make_sut(sut_name)
        sut_meta.append(
            {"name": sut.name, "version": sut.version, "capabilities": sorted(sut.capabilities)}
        )
        for scenario in scenarios:
            print(f"  [{sut.name}] {scenario.id} {scenario.title} …", flush=True)
            metrics, wall = _run_scenario(sut, scenario)
            runs.append(ScenarioRun(sut.name, scenario.slug, scenario.id, scenario.version, wall, metrics))

    _write_outputs(run_dir, sut_meta, scenarios, runs)
    return run_dir


def _write_outputs(run_dir: Path, sut_meta, scenarios, runs: list[ScenarioRun]) -> None:
    # per-scenario jsonl
    by_scenario: dict[str, list[ScenarioRun]] = {}
    for r in runs:
        by_scenario.setdefault(r.scenario, []).append(r)
    for slug, sruns in by_scenario.items():
        lines = []
        for sr in sruns:
            for m in sr.metrics:
                lines.append(json.dumps({
                    "scenario": sr.scenario_id, "version": sr.version, "sut": sr.sut,
                    **m.as_dict(),
                }))
        (run_dir / "scenarios" / f"{slug}.jsonl").write_text("\n".join(lines) + "\n")

    # manifest
    manifest = {
        "run_id": run_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "harness_version": __version__,
        "git_sha": _git_sha(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "suts": sut_meta,
        "scenarios": [{"id": s.id, "slug": s.slug, "version": s.version, "title": s.title} for s in scenarios],
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # timing.json + cost.json
    timing = {r.sut: {} for r in runs}
    cost = {r.sut: {} for r in runs}
    for r in runs:
        timing[r.sut][r.scenario_id] = round(r.wall_ms, 2)
        usd = 0.0
        for m in r.metrics:
            if m.metric.endswith("_$_per_1k") and isinstance(m.value, (int, float)):
                usd += float(m.value)
        cost[r.sut][r.scenario_id] = round(usd, 4)
    (run_dir / "timing.json").write_text(json.dumps(timing, indent=2))
    (run_dir / "cost.json").write_text(json.dumps(cost, indent=2))

    # judgements.jsonl placeholder (no LLM judge used by deterministic scenarios yet)
    (run_dir / "judgements.jsonl").write_text("")

    (run_dir / "summary.md").write_text(_summary_md(manifest, runs))


def _summary_md(manifest: dict, runs: list[ScenarioRun]) -> str:
    suts = [s["name"] for s in manifest["suts"]]
    lines = [
        f"# dinomem-bench run `{manifest['run_id']}`",
        "",
        f"- harness {manifest['harness_version']} · python {manifest['python']} · git {manifest['git_sha']}",
        f"- SUTs: {', '.join(suts)}",
        "",
    ]
    # index metrics by (scenario_id, metric) -> {sut: (value,status)}
    rows: dict[tuple[str, str], dict[str, tuple]] = {}
    order: list[tuple[str, str]] = []
    counts = {s: {"pass": 0, "fail": 0, "na": 0, "crash": 0, "info": 0} for s in suts}
    for r in runs:
        for m in r.metrics:
            key = (r.scenario_id, m.metric)
            if key not in rows:
                rows[key] = {}
                order.append(key)
            rows[key][r.sut] = (m.value, m.status)
            counts[r.sut][m.status] = counts[r.sut].get(m.status, 0) + 1

    lines.append("## Scorecard")
    lines.append("")
    lines.append("| Scenario | Metric | " + " | ".join(suts) + " |")
    lines.append("|---|---|" + "|".join(["---"] * len(suts)) + "|")
    mark = {"pass": "✅", "fail": "❌", "na": "—", "crash": "💥", "info": "ℹ️"}
    for (sid, metric) in order:
        cells = []
        for s in suts:
            if s in rows[(sid, metric)]:
                v, st = rows[(sid, metric)][s]
                cells.append(f"{mark.get(st,'')} {v}")
            else:
                cells.append("")
        lines.append(f"| {sid} | {metric} | " + " | ".join(cells) + " |")

    lines += ["", "## Totals", "", "| SUT | pass | fail | N/A | crash | info |", "|---|---|---|---|---|---|"]
    for s in suts:
        c = counts[s]
        lines.append(f"| {s} | {c['pass']} | {c['fail']} | {c['na']} | {c['crash']} | {c['info']} |")
    lines.append("")
    return "\n".join(lines)
