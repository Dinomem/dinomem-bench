# agentmem-bench — cross-system comparison

Generated from 16 run(s) in `runs/`. Per (SUT, scenario) the most
recent run with real metrics is used (provenance at the bottom). FakeSUT is
the in-process reference, not a system under test.

## Scorecard

| Scenario | Metric | pgvector | mem0 | zep | supermemory | langmem | agentmem | fake |
|---|---|---|---|---|---|---|---|---|
| S1 | C1.detected | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S1 | C1.resolved | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y | ✅ Y |
| S1 | C1.consistent | ✅ Y | ✅ Y | ✅ Y | ✅ Y | ✅ Y | ✅ Y | ✅ Y |
| S2 | T1.bitemporal | ℹ️ N | ℹ️ N | ℹ️ Y | ℹ️ N | ℹ️ N | ℹ️ Y | ℹ️ Y |
| S2 | T1.t0 | — N/A | — N/A | ✅ Y | — N/A | — N/A | ❌ N | ✅ Y |
| S2 | T1.t1 | — N/A | — N/A | ✅ Y | — N/A | — N/A | ❌ N | ✅ Y |
| S3 | S3.isolated | ✅ Y | ✅ Y | — N/A | ✅ Y | ✅ Y | ✅ Y | ✅ Y |
| S3 | S3.team_visible | ✅ Y | ❌ N | — N/A | ❌ N | ✅ Y | ✅ Y | ✅ Y |
| S3 | S3.cross_workflow | ✅ Y | ✅ Y | — N/A | ✅ Y | ✅ Y | ✅ Y | ✅ Y |
| S4 | S4.converge | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y |
| S4 | S4.lossless | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y |
| S4 | S4.deterministic | — N/A | — N/A | — N/A | — N/A | — N/A | — N/A | ✅ Y |
| S5 | S5.leakage_rate | ✅ 0.0% | ✅ 0.0% | — N/A | ✅ 0.0% | ✅ 0.0% | · | ✅ 0.0% |
| S6 | P.ignore.correct | — N/A | — N/A | — N/A | — N/A | — N/A | · | ✅ Y |
| S6 | P.timestamp_wins.correct | — N/A | — N/A | — N/A | — N/A | — N/A | · | ✅ Y |
| S6 | P.planner_wins.correct | — N/A | — N/A | — N/A | — N/A | — N/A | · | ✅ Y |
| S6 | P.human_in_loop.correct | — N/A | — N/A | — N/A | — N/A | — N/A | · | ✅ Y |
| S6 | P.human_in_loop.surfaced | — N/A | — N/A | — N/A | — N/A | — N/A | · | ✅ Y |
| S6 | s6_policy.run | · | · | · | · | · | 💥 crash | · |
| S7 | Op.write_p50_ms | ℹ️ 307.395 | ℹ️ 1142.688 | ℹ️ 304.815 | ℹ️ 2221.558 | ℹ️ 302.811 | · | ℹ️ 0.038 |
| S7 | Op.write_p95_ms | ℹ️ 451.54 | ℹ️ 1450.572 | ℹ️ 416.372 | ℹ️ 7172.466 | ℹ️ 404.217 | · | ℹ️ 0.11 |
| S7 | Op.search_p50_ms | ℹ️ 308.97 | ℹ️ 507.021 | ℹ️ 302.367 | ℹ️ 1869.841 | ℹ️ 304.328 | · | ℹ️ 0.28 |
| S7 | Op.search_p95_ms | ℹ️ 510.516 | ℹ️ 596.981 | ℹ️ 406.26 | ℹ️ 9377.719 | ℹ️ 412.138 | · | ℹ️ 0.535 |
| S7 | Op.write_$_per_1k | ℹ️ 0.0001 | ℹ️ 0.0 | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | · | ℹ️ 0.0 |
| S7 | Op.search_$_per_1k | ℹ️ 0.0001 | ℹ️ 0.0 | ℹ️ N/A | ℹ️ N/A | ℹ️ N/A | · | ℹ️ 0.0 |

## Totals (selected results)

| SUT | pass | fail | N/A | crash | info |
|---|---|---|---|---|---|
| pgvector | 5 | 0 | 12 | 0 | 7 |
| mem0 | 4 | 1 | 12 | 0 | 7 |
| zep | 3 | 0 | 14 | 0 | 7 |
| supermemory | 4 | 1 | 12 | 0 | 7 |
| langmem | 5 | 0 | 12 | 0 | 7 |
| agentmem | 6 | 2 | 3 | 1 | 1 |
| fake | 17 | 0 | 0 | 0 | 7 |

## Provenance

| SUT | scenario | run |
|---|---|---|
| agentmem | S1 | `2026-06-12-133803` |
| agentmem | S2 | `2026-06-12-134438` |
| agentmem | S3 | `2026-06-12-133803` |
| agentmem | S4 | `2026-06-12-133803` |
| agentmem | S6 | `2026-06-12-135321` |
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
| langmem | S7 | `2026-06-13-044637` |
| mem0 | S1 | `2026-06-12-141044` |
| mem0 | S2 | `2026-06-12-141044` |
| mem0 | S3 | `2026-06-12-141044` |
| mem0 | S4 | `2026-06-12-141044` |
| mem0 | S5 | `2026-06-12-141350` |
| mem0 | S6 | `2026-06-12-141044` |
| mem0 | S7 | `2026-06-12-141350` |
| pgvector | S1 | `2026-06-12-012323` |
| pgvector | S2 | `2026-06-12-012323` |
| pgvector | S3 | `2026-06-12-012323` |
| pgvector | S4 | `2026-06-12-012323` |
| pgvector | S5 | `2026-06-12-012323` |
| pgvector | S6 | `2026-06-12-012323` |
| pgvector | S7 | `2026-06-12-012323` |
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
| zep | S7 | `2026-06-12-164216` |
