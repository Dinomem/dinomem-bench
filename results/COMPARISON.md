# dinomem-bench — cross-system comparison

> **Conflict of interest / integrity.** DinoMem's maintainers build *and* run
> this benchmark, and **DinoMem is one of the systems under test**. To keep that
> from biasing the result we: publish the full harness + the deterministic
> assertions that decide every metric (no LLM-judge — see [`METHODOLOGY.md`](../METHODOLOGY.md));
> record provenance (run id, git sha, pinned models) for every cell; **report
> every metric, including the ones DinoMem fails or is N/A on** (enumerated in
> *Where DinoMem loses / is N/A* below); test all systems only through their
> public, black-box APIs; and invite competitors to PR their own adapters /
> config overrides (maintainers keep merge rights on harness code only — see
> [`CONTRIBUTING.md`](../CONTRIBUTING.md)). DinoMem is one SUT here, not the
> subject of this repo.

Generated from 20 run(s) in `runs/`. Per (SUT, scenario) the most
recent run with real metrics is used (provenance at the bottom). FakeSUT is
the in-process reference, not a system under test.

## Scorecard

| Scenario | Metric | pgvector | mem0 | zep | cognee | supermemory | langmem | dinomem | fake |
|---|---|---|---|---|---|---|---|---|---|
| S1 | C1.detected | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S1 | C1.resolved | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S1 | C1.consistent | ✅ Y | ✅ Y | ✅ Y | ✅ Y | ✅ Y | ✅ Y | ✅ Y | ✅ Y |
| S2 | T1.bitemporal | ℹ️ N | ℹ️ N | ℹ️ Y | ℹ️ N | ℹ️ N | ℹ️ N | ℹ️ Y | ℹ️ Y |
| S2 | T1.t0 | — N/A | — N/A | ✅ Y | — N/A | — N/A | — N/A | ❌ N | ✅ Y |
| S2 | T1.t1 | — N/A | — N/A | ✅ Y | — N/A | — N/A | — N/A | ❌ N | ✅ Y |
| S3 | S3.isolated | ✅ Y | ✅ Y | — N/A | — N/A | ✅ Y | ✅ Y | ✅ Y | ✅ Y |
| S3 | S3.team_visible | ✅ Y | ❌ N | — N/A | — N/A | ❌ N | ✅ Y | ✅ Y | ✅ Y |
| S3 | S3.cross_workflow | ✅ Y | ✅ Y | — N/A | — N/A | ✅ Y | ✅ Y | ✅ Y | ✅ Y |
| S4 | S4.converge | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y |
| S4 | S4.lossless | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y |
| S4 | S4.deterministic | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y |
| S5 | S5.leakage_rate | ✅ 0.0% | ✅ 0.0% | — N/A | — N/A | ✅ 0.0% | ✅ 0.0% | ✅ 0.0% | ✅ 0.0% |
| S6 | P.ignore.correct | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S6 | P.timestamp_wins.correct | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S6 | P.planner_wins.correct | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S6 | P.human_in_loop.correct | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S6 | P.human_in_loop.surfaced | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S7 | Op.write_p50_ms | ℹ️ 469.936 | ℹ️ 1082.409 | ℹ️ 299.544 | ℹ️ 20965.427 | ℹ️ 2221.558 | ℹ️ 270.821 | ℹ️ 1004.919 | ℹ️ 0.038 |
| S7 | Op.write_p95_ms | ℹ️ 725.338 | ℹ️ 1498.432 | ℹ️ 405.428 | ℹ️ 28167.986 | ℹ️ 7172.466 | ℹ️ 443.994 | ℹ️ 1084.248 | ℹ️ 0.11 |
| S7 | Op.search_p50_ms | ℹ️ 454.124 | ℹ️ 504.534 | ℹ️ 312.274 | ℹ️ 1918.594 | ℹ️ 1869.841 | ℹ️ 307.87 | ℹ️ 891.796 | ℹ️ 0.28 |
| S7 | Op.search_p95_ms | ℹ️ 618.059 | ℹ️ 745.254 | ℹ️ 413.591 | ℹ️ 1926.687 | ℹ️ 9377.719 | ℹ️ 478.147 | ℹ️ 1116.618 | ℹ️ 0.535 |
| S7 | Op.write_$_per_1k | ℹ️ 0.0001 | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ 0.0 |
| S7 | Op.search_$_per_1k | ℹ️ 0.0001 | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | ℹ️ 0.0 |
| S7 | Op.write_mean_ms | ℹ️ 518.805 | ℹ️ 1119.504 | ℹ️ 322.1 | · | · | ℹ️ 319.55 | · | · |
| S7 | Op.write_p99_ms | ℹ️ 1425.201 | ℹ️ 1661.029 | ℹ️ 767.781 | · | · | ℹ️ 941.526 | · | · |
| S7 | Op.search_mean_ms | ℹ️ 484.166 | ℹ️ 554.355 | ℹ️ 338.94 | · | · | ℹ️ 329.69 | · | · |
| S7 | Op.search_p99_ms | ℹ️ 820.359 | ℹ️ 1290.972 | ℹ️ 427.432 | · | · | ℹ️ 621.956 | · | · |

## Totals (selected results)

| SUT | pass | fail | N/A | crash | info |
|---|---|---|---|---|---|
| pgvector | 5 | 0 | 12 | 0 | 11 |
| mem0 | 4 | 1 | 12 | 0 | 11 |
| zep | 3 | 0 | 14 | 0 | 11 |
| cognee | 1 | 0 | 16 | 0 | 7 |
| supermemory | 4 | 1 | 12 | 0 | 7 |
| langmem | 5 | 0 | 12 | 0 | 11 |
| dinomem | 12 | 2 | 3 | 0 | 7 |
| fake | 17 | 0 | 0 | 0 | 7 |

## Where DinoMem loses / is N/A

DinoMem is reported like every other system under test. Across the selected results it **fails 2**, **crashes on 0**, and is **N/A on 3** metric cell(s). Every one is listed below (passes/operational `info` are in the scorecard above; this section is only the non-wins):

### ❌ Fails (wrong answer vs the scenario assertion)

| Scenario | Metric | DinoMem value | Note |
|---|---|---|---|
| S2 | T1.t0 | ❌ N |  |
| S2 | T1.t1 | ❌ N |  |

### 💥 Crashes (raised / 5xx / timeout, after the one re-run)

_None — DinoMem has no `crash` cells in these results._

### — N/A (DinoMem's API can't perform this metric — not a failure)

| Scenario | Metric | DinoMem value | Note |
|---|---|---|---|
| S4 | S4.converge | — N/A | shared: every real system is N/A here too |
| S4 | S4.lossless | — N/A | shared: every real system is N/A here too |
| S4 | S4.deterministic | — N/A | shared: every real system is N/A here too |

_Reading this honestly: S2 temporal (`T1.t0`/`T1.t1`) is a real **failure** — DinoMem accepts `at_time` but returns both the old and new fact, where Zep correctly invalidates the stale one. S4 CRDT is **N/A for every system, DinoMem included** — no shipping system exposes a black-box replica/vector-clock API the convergence test can drive (CRDT is a DinoMem V3 roadmap item, not a measured guarantee). Any crash cell is a genuine backend defect, not hidden._

## Provenance

| SUT | scenario | run |
|---|---|---|
| cognee | S1 | `2026-06-13-053651` |
| cognee | S2 | `2026-06-13-053651` |
| cognee | S3 | `2026-06-13-054802` |
| cognee | S4 | `2026-06-13-053651` |
| cognee | S5 | `2026-06-13-054802` |
| cognee | S6 | `2026-06-13-053651` |
| cognee | S7 | `2026-06-13-053651` |
| dinomem | S1 | `2026-06-12-133803` |
| dinomem | S2 | `2026-06-12-134438` |
| dinomem | S3 | `2026-06-12-133803` |
| dinomem | S4 | `2026-06-12-133803` |
| dinomem | S5 | `2026-06-13-055841` |
| dinomem | S6 | `2026-06-13-085930` |
| dinomem | S7 | `2026-06-13-055841` |
| fake | S1 | `2026-06-12-132140` |
| fake | S2 | `2026-06-12-132140` |
| fake | S3 | `2026-06-12-132140` |
| fake | S4 | `2026-06-12-132140` |
| fake | S5 | `2026-06-12-132140` |
| fake | S6 | `2026-06-12-132140` |
| fake | S7 | `2026-06-12-142056` |
| langmem | S1 | `2026-06-13-044637` |
| langmem | S2 | `2026-06-13-044637` |
| langmem | S3 | `2026-06-13-044637` |
| langmem | S4 | `2026-06-13-044637` |
| langmem | S5 | `2026-06-13-044637` |
| langmem | S6 | `2026-06-13-044637` |
| langmem | S7 | `2026-06-13-094031` |
| mem0 | S1 | `2026-06-12-141044` |
| mem0 | S2 | `2026-06-12-141044` |
| mem0 | S3 | `2026-06-12-141044` |
| mem0 | S4 | `2026-06-12-141044` |
| mem0 | S5 | `2026-06-12-141350` |
| mem0 | S6 | `2026-06-12-141044` |
| mem0 | S7 | `2026-06-13-094536` |
| pgvector | S1 | `2026-06-12-012323` |
| pgvector | S2 | `2026-06-12-012323` |
| pgvector | S3 | `2026-06-12-012323` |
| pgvector | S4 | `2026-06-12-012323` |
| pgvector | S5 | `2026-06-12-012323` |
| pgvector | S6 | `2026-06-12-012323` |
| pgvector | S7 | `2026-06-13-094143` |
| supermemory | S1 | `2026-06-12-152222` |
| supermemory | S2 | `2026-06-12-152222` |
| supermemory | S3 | `2026-06-12-153911` |
| supermemory | S4 | `2026-06-12-152222` |
| supermemory | S5 | `2026-06-12-152222` |
| supermemory | S6 | `2026-06-12-152222` |
| supermemory | S7 | `2026-06-12-152222` |
| zep | S1 | `2026-06-12-164216` |
| zep | S2 | `2026-06-12-163940` |
| zep | S3 | `2026-06-12-164216` |
| zep | S4 | `2026-06-12-164216` |
| zep | S5 | `2026-06-12-164216` |
| zep | S6 | `2026-06-12-164216` |
| zep | S7 | `2026-06-13-094327` |
