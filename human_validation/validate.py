"""Human-validation harness: show the deterministic assertion verdict next to a
hand-checked 'human says' verdict for a small sample of scenario cases, and assert
they agree. Stdlib-only, no network, deterministic.

    python3 human_validation/validate.py           # regenerate samples.jsonl + SAMPLE.md, check
    python3 human_validation/validate.py --check    # check only; fail (exit 1) on drift/disagreement

The point: the benchmark has no LLM-as-judge, so the assertions ARE the judge.
This file is the evidence that those assertions match human judgement — including
on the cases where the maintainers' own system (DinoMem) loses.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dinomem_bench.scenarios.base import FAIL, NA, PASS  # noqa: E402
from dinomem_bench.suts.fake import FakeSUT  # noqa: E402

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples.jsonl"
SAMPLE_MD = HERE / "SAMPLE.md"


# --- live in-process cases (recomputed, not transcribed) --------------------
def _fake_s1_resolved() -> str:
    """S1 C1.resolved on the reference FakeSUT under planner_wins: read returns
    only the planner's 'friday'. Returns the deterministic status."""
    from dinomem_bench.scenarios.s1_contradictory import S1Contradictory

    sut = FakeSUT()
    sut.setup()
    metrics = {m.metric: m for m in S1Contradictory().run(sut)}
    sut.teardown()
    return metrics["C1.resolved"].status


def _fake_s4_converge() -> str:
    from dinomem_bench.scenarios.s4_crdt import S4Crdt

    sut = FakeSUT()
    sut.setup()
    metrics = {m.metric: m for m in S4Crdt().run(sut)}
    sut.teardown()
    return metrics["S4.converge"].status


def _minimal_s4_na() -> str:
    """A capability-less store must record N/A (not fail) on S4."""
    from dinomem_bench.scenarios.s4_crdt import S4Crdt
    from dinomem_bench.adapter import SUTAdapter
    from dinomem_bench.types import Hit, WriteResult
    from datetime import datetime

    class MinimalSUT(SUTAdapter):
        name = "minimal"
        capabilities = frozenset()

        def setup(self):
            self._rows = []

        def write(self, content, *, agent_id, scope="team", role=None, workflow_id=None):
            self._rows.append(content)
            return WriteResult(id=str(len(self._rows)), created_at=datetime(2026, 1, 1))

        def search(self, query, *, agent_id, workflow_id=None, top_k=5, at_time=None):
            return [Hit(id="1", content=c, agent_id="a", scope="team",
                        created_at=datetime(2026, 1, 1)) for c in self._rows if query.lower() in c.lower()]

    sut = MinimalSUT()
    sut.setup()
    metrics = {m.metric: m for m in S4Crdt().run(sut)}
    return metrics["S4.converge"].status


# --- the committed sample ---------------------------------------------------
# Each case pairs the deterministic assertion verdict with a hand-checked human
# verdict. In-process cases recompute `assertion` live; published real-system
# cases carry the verdict observed in results/COMPARISON.md (no network needed to
# state a fact already measured + committed there).
def build_samples() -> list[dict]:
    cases: list[dict] = [
        {
            "scenario": "S1", "sut": "fake", "metric": "C1.resolved",
            "inputs": "policy=planner_wins; planner writes 'Deadline is Friday', executor writes 'Deadline is Monday'; read 'Deadline'",
            "system_returned": "only 'Deadline is Friday'",
            "assertion": _fake_s1_resolved(),
            "assertion_rule": "pass iff read has 'friday' and NOT 'monday'",
            "human_says": PASS,
            "human_rationale": "planner_wins means the planner's fact must win on read and the executor's must be suppressed. Returning only 'Friday' is exactly correct.",
        },
        {
            "scenario": "S4", "sut": "fake", "metric": "S4.converge",
            "inputs": "R1 writes 'Owner is Alice', R2 writes 'Owner is Bob' (disjoint vclocks); sync in reversed order; compare replica states",
            "system_returned": "R1 state == R2 state",
            "assertion": _fake_s4_converge(),
            "assertion_rule": "pass iff replica_state('R1') == replica_state('R2')",
            "human_says": PASS,
            "human_rationale": "A convergent (CRDT) system must reach identical state on both replicas regardless of delivery order. Equal states is the right verdict; the reference impl earns it.",
        },
        {
            "scenario": "S4", "sut": "minimal", "metric": "S4.converge",
            "inputs": "same S4 protocol against a store with NO vector-clock/replica API",
            "system_returned": "Unsupported (no replica API)",
            "assertion": _minimal_s4_na(),
            "assertion_rule": "na (not fail) when the SUT lacks VECTOR_CLOCK / raises Unsupported",
            "human_says": NA,
            "human_rationale": "A store that never claimed CRDT semantics must NOT be marked as failing — it simply can't run the test. N/A is the fair verdict, not fail.",
        },
        {
            "scenario": "S2", "sut": "dinomem", "metric": "T1.t1",
            "inputs": "write 'status is green' @T0, then 'status is red' @T1; read at_time=T1",
            "system_returned": "both 'green' and 'red' (observed in results/COMPARISON.md)",
            "assertion": FAIL,
            "assertion_rule": "pass iff read at T1 has 'red' and NOT 'green'",
            "human_says": FAIL,
            "human_rationale": "At T1 the only valid fact is 'red'; the earlier 'green' was superseded. Returning the stale fact too is wrong. This is the maintainers' OWN system failing, and the assertion correctly marks it fail — not na, because DinoMem does accept at_time.",
        },
        {
            "scenario": "S2", "sut": "zep", "metric": "T1.t1",
            "inputs": "same as above against Zep",
            "system_returned": "only 'red' (observed in results/COMPARISON.md)",
            "assertion": PASS,
            "assertion_rule": "pass iff read at T1 has 'red' and NOT 'green'",
            "human_says": PASS,
            "human_rationale": "Zep invalidates the stale fact (invalid_at) so the temporal read returns only the fact valid at T1. Correctly a pass — confirming the assertion is not rigged against non-DinoMem systems either.",
        },
        {
            "scenario": "S3", "sut": "mem0", "metric": "S3.team_visible",
            "inputs": "A writes private then re-writes the SAME fact at team scope; B (same workflow) searches",
            "system_returned": "0 hits — B still cannot see it (observed in results/COMPARISON.md)",
            "assertion": FAIL,
            "assertion_rule": "pass iff B sees > 0 hits after the team re-write",
            "human_says": FAIL,
            "human_rationale": "Once A publishes the fact at team scope, a teammate must be able to see it. mem0's content dedup ignores the scope change and keeps it hidden — a genuine wrong answer, correctly fail.",
        },
    ]
    for c in cases:
        c["agree"] = c["assertion"] == c["human_says"]
    return cases


def render_md(cases: list[dict]) -> str:
    lines = [
        "# Human-validation sample",
        "",
        "Deterministic assertion verdict vs a hand-checked human verdict. `agree`",
        "is `true` on every row — evidence the assertions match human judgement,",
        "including where DinoMem loses (S2) and where a store with no replica API is N/A (S4).",
        "Regenerate with `python3 human_validation/validate.py`.",
        "",
        "| Scenario | SUT | Metric | System returned | Assertion | Human says | Agree |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in cases:
        lines.append(
            f"| {c['scenario']} | {c['sut']} | {c['metric']} | {c['system_returned']} "
            f"| {c['assertion']} | {c['human_says']} | {'✅' if c['agree'] else '❌ DISAGREE'} |"
        )
    lines += ["", "See `samples.jsonl` for the full rule + rationale per case.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true",
                   help="do not rewrite files; fail if committed samples drift or any case disagrees")
    args = p.parse_args(argv)

    cases = build_samples()
    disagreements = [c for c in cases if not c["agree"]]

    new_jsonl = "\n".join(json.dumps(c) for c in cases) + "\n"
    new_md = render_md(cases)

    if args.check:
        ok = True
        if not SAMPLES.exists() or SAMPLES.read_text() != new_jsonl:
            print("DRIFT: samples.jsonl is stale — re-run without --check.", file=sys.stderr)
            ok = False
        if disagreements:
            for c in disagreements:
                print(f"DISAGREEMENT: {c['scenario']} {c['sut']} {c['metric']}: "
                      f"assertion={c['assertion']} human={c['human_says']}", file=sys.stderr)
            ok = False
        print(f"{len(cases) - len(disagreements)}/{len(cases)} cases agree.")
        return 0 if ok else 1

    SAMPLES.write_text(new_jsonl)
    SAMPLE_MD.write_text(new_md)
    if disagreements:
        for c in disagreements:
            print(f"DISAGREEMENT: {c['scenario']} {c['sut']} {c['metric']}", file=sys.stderr)
        print(f"\n{len(disagreements)} case(s) disagree — fix the assertion or the human verdict.",
              file=sys.stderr)
        return 1
    print(f"wrote {SAMPLES.name} + {SAMPLE_MD.name}: {len(cases)} cases, all agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
