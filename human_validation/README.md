# Human validation of the deterministic assertions

The benchmark has **no LLM-as-judge** — every metric is decided by a deterministic
Python assertion (see [`../METHODOLOGY.md`](../METHODOLOGY.md)). That is a
reproducibility strength, but it raises a fair question: **are the assertions
themselves correct and fair?** A wrong assertion would mislabel a correct system,
or quietly favour the maintainers' own system (DinoMem).

This directory is the answer: a small, committed, **deterministic, no-network**
sample of scenario cases where we show, side by side:

1. the inputs the scenario fed the system,
2. what the system returned (for the in-process cases, computed live; for the
   real-system cases, the observed outcome already published in
   [`../results/COMPARISON.md`](../results/COMPARISON.md)),
3. the **deterministic assertion's verdict** (`pass` / `fail` / `na`),
4. a **"human says" verdict** — a hand-checked judgement of what the *right*
   answer is, written by a person reading the scenario, and
5. whether they **agree**.

If the assertion and the human ever disagree, that's a bug in the assertion and is
flagged loudly. In this committed sample they agree on every case, which is the
evidence that the assertions are fair — including on the cases where **DinoMem
loses** (S2 temporal fail) and where **every system is N/A** (S4 CRDT).

## Files

| File | What it is |
|---|---|
| `samples.jsonl` | The committed sample: one JSON object per validated case. |
| `validate.py` | Regenerates `samples.jsonl` deterministically (stdlib-only, no network) and **asserts assertion-vs-human agreement**. Exits non-zero on any disagreement. |
| `SAMPLE.md` | A human-readable rendering of `samples.jsonl` (the same data as a table). |

## Reproduce

```bash
python3 human_validation/validate.py            # regenerate + check agreement
python3 human_validation/validate.py --check     # check only, fail on drift
```

`validate.py` runs the in-process `FakeSUT` (the gold-standard reference) and a
capability-less `MinimalSUT` live to produce the deterministic verdicts for the
S1/S3/S4 cases — so those rows are recomputed, not hand-transcribed. The S2/S3
**real-system** rows (DinoMem fails S2; mem0 fails `S3.team_visible`) carry the
verdict observed in the published matrix; the "human says" column explains why a
human reaches the same call. No network or API key is required.

## How to read a row

```json
{
  "scenario": "S2", "sut": "dinomem", "metric": "T1.t1",
  "inputs": "write 'status is green' @T0, 'status is red' @T1; read at_time=T1",
  "system_returned": "both 'green' and 'red'",
  "assertion": "fail",
  "assertion_rule": "pass iff result has 'red' and NOT 'green'",
  "human_says": "fail",
  "human_rationale": "At T1 the only valid fact is 'red'. Returning the superseded 'green' too is wrong — a temporal query must hide stale facts.",
  "agree": true
}
```

`agree: true` on every row is the validation. This is deliberately lightweight and
honest: a handful of cases that demonstrate the assertions match human judgement,
including against the maintainers' own system.
