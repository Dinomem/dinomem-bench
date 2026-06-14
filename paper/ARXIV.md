# arXiv submission guide — dinomem-bench

## Build & package

```bash
cd paper
make            # -> dinomem-bench.pdf (proofread this)
make arxiv      # -> dinomem-bench-arxiv.tar.gz  (the file you upload)
```

`make arxiv` produces a self-contained tarball containing `dinomem-bench.tex`,
`dinomem-bench.bbl` (generated — so arXiv doesn't re-run BibTeX), and
`figures/*.pdf`. arXiv compiles it with `pdflatex` by default; all packages used
are in arXiv's standard TeX Live.

## Before you upload — fill these in (`dinomem-bench.tex`)

- [ ] **Author + affiliation + email** (currently placeholder `Aneesh / devsforfun`).
      Add ORCID if you have one.
- [ ] **Fix the date** if you don't want `\today` (e.g. `\date{June 2026}`).
- [ ] **Proofread the PDF** — especially the results table and the COI section.
- [ ] Decide whether to keep the "working draft" framing or finalize it.

## Suggested arXiv metadata (web submission form)

- **Primary category:** `cs.MA` (Multiagent Systems) — best topical fit.
- **Cross-list:** `cs.AI` (Artificial Intelligence), `cs.DB` (Databases),
  `cs.SE` (Software Engineering — it is a benchmark/harness).
- **License:** `CC BY 4.0` recommended (matches the repo's open posture; lets
  others reuse the figures/methodology with attribution).
- **Comments field:** e.g. *"Code, scenarios, and all raw run logs:
  https://github.com/DinoMem/dinomem-bench"* — and, given §10, you may also
  state the conflict of interest here.

## Abstract (paste into the form)

> Existing agent-memory benchmarks (LoCoMo, LongMemEval) evaluate a single agent
> recalling information from one long conversation. We argue this misses the
> dominant failure mode of multi-agent systems, where memory is shared and the hard
> problems are coordination: contradictory writes, temporal validity, scope leakage,
> concurrent-write convergence, and conflict-resolution policy. We introduce
> dinomem-bench, a reproducible benchmark of seven deterministic scenarios (S1–S7)
> that isolate these properties, and evaluate seven shipped memory systems (DinoMem,
> Mem0, Zep, Cognee, Supermemory, LangMem, and a raw pgvector baseline) behind a
> uniform black-box adapter, with an in-process reference implementation that
> validates the scenarios themselves. We report per-scenario, per-metric results —
> not a single score — and find the capability space sharply non-uniform:
> contradiction detection/resolution and conflict policies are provided by exactly
> one system; bitemporal "what was true at T?" retrieval by exactly one other system;
> CRDT convergence by none, because no shipping system exposes a replica API to a
> black-box test; and a raw vector store matches the managed systems on every
> property that does not require coordination machinery. Beyond the grid, running the
> benchmark surfaced reproducible operational failures. We release the harness,
> scenarios, and complete run logs, and disclose prominently that the benchmark's
> authors also build one of the systems under test.

## Notes
- arXiv re-renders from source; the `.pdf` you build locally is for proofing only
  (do **not** upload a pre-built PDF for a TeX submission).
- If arXiv's compiler complains about a missing package, it is almost always a
  stale cache — the packages here are all standard. Worst case, inline the `.bbl`
  (already shipped) and remove the `\bibliography` line in favor of a `thebibliography`
  block.
- Keep `runs/` out of the upload (it's gitignored and not needed for the paper).
