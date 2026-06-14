# Human-validation sample

Deterministic assertion verdict vs a hand-checked human verdict. `agree`
is `true` on every row — evidence the assertions match human judgement,
including where DinoMem loses (S2) and where a store with no replica API is N/A (S4).
Regenerate with `python3 human_validation/validate.py`.

| Scenario | SUT | Metric | System returned | Assertion | Human says | Agree |
|---|---|---|---|---|---|---|
| S1 | fake | C1.resolved | only 'Deadline is Friday' | pass | pass | ✅ |
| S4 | fake | S4.converge | R1 state == R2 state | pass | pass | ✅ |
| S4 | minimal | S4.converge | Unsupported (no replica API) | na | na | ✅ |
| S2 | dinomem | T1.t1 | both 'green' and 'red' (observed in results/COMPARISON.md) | fail | fail | ✅ |
| S2 | zep | T1.t1 | only 'red' (observed in results/COMPARISON.md) | pass | pass | ✅ |
| S3 | mem0 | S3.team_visible | 0 hits — B still cannot see it (observed in results/COMPARISON.md) | fail | fail | ✅ |

See `samples.jsonl` for the full rule + rationale per case.
