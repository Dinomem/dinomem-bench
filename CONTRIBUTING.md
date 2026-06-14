# Contributing

> **Why this file exists.** DinoMem's maintainers build *and* run this benchmark,
> and DinoMem is one of the systems under test. The honest answer to "how do we
> know it's not rigged?" is: **the harness, the assertions, and the data are all
> public, and competitors can submit their own adapters and config overrides.**
> This file is the convention for doing exactly that.

There are two very different kinds of contribution, with two different review bars.

## 1. Adapter / config contributions — *yours to own*

If you maintain (or just want to fairly represent) a memory system, you can:

- **Add or fix a SUT adapter** under `dinomem_bench/suts/<your_sut>.py`, or
- **Submit a config override** under `configs/<your_sut>.json` (model, version,
  endpoint, index/tuning knobs).

The knob values — *which* model, *which* version, *which* endpoint, *which* tuning
— are **yours**. Maintainers do not get to pick a weak configuration for a
competitor and a strong one for DinoMem; that is the whole point. We review these
PRs only for **fairness rules**, not to second-guess your tuning:

- **Black-box, public APIs only.** The adapter must talk to the system the way any
  user would (public client / HTTP API). No privileged internals, no reading
  another system's private tables.
- **Pinned versions, no `latest`.** Pin the model/package version (add it to
  `dinomem_bench/models.py` if it's a model with a price). Determinism depends on
  this.
- **No secrets in the repo.** API keys live in environment variables, never in a
  `configs/*.json` file.
- **Capabilities declared honestly.** Advertise only the `Capability` flags your
  system actually supports; methods it can't do should raise `Unsupported` (→
  scored `N/A`, not a crash, not a fake pass).

### How config override works

`dinomem_bench/config.py` resolves each knob `env > configs/<sut>.json > default`.
To make a knob overridable, read it in your adapter's `setup()`:

```python
from ..config import load as load_config
cfg = load_config("pgvector")
embed_model = cfg.get("embed_model", OPENAI_EMBED_3_SMALL.name, env="PGVECTOR_EMBED_MODEL")
lists = cfg.get_int("ivfflat_lists", 100, env="PGVECTOR_IVFFLAT_LISTS")
```

`suts/pgvector.py` and `suts/langmem.py` are the worked examples; see
[`configs/README.md`](./configs/README.md).

### Adding a brand-new SUT

1. Subclass `dinomem_bench.adapter.SUTAdapter`; implement `write` / `search` and
   whatever of `check_conflicts` / `set_policy` / `pending_events` / `replica_*`
   your system supports. Import the system's SDK **inside** the methods (lazy).
2. Set `capabilities` to the flags it genuinely supports.
3. Register a **lazy factory** in `dinomem_bench/suts/__init__.py` (import inside
   the factory so selecting another SUT never pulls your deps).
4. Add an optional-dependency extra in `pyproject.toml` (`[project.optional-dependencies]`).
5. Add `configs/<sut>.json` documenting its knobs.
6. Run `python3 tests/test_smoke.py` and `ruff check .` before opening the PR.

## 2. Harness / scoring contributions — *maintainers keep merge rights*

Changes to **how a metric is decided** — the scenarios (`scenarios/sN_*.py`), the
runner, `compare.py`, `config.py`, the metric-status semantics, the determinism
guarantees — are different. **Maintainers keep final merge rights on harness code
only**, because a change here moves *every* system's score, including DinoMem's, so
it must be scrutinised for whether it advantages the home system.

We welcome harness PRs (better assertions, new scenarios, bug fixes) — but expect:

- a clear statement of *which metric verdicts change and why*, for **all** SUTs;
- the change reflected in [`METHODOLOGY.md`](./METHODOLOGY.md) (the published
  scoring rules) in the same PR;
- `tests/test_smoke.py` still green (FakeSUT passes all correctness; a
  capability-less SUT records `N/A`, never a hard fail);
- if it touches the home system's outcome, a note in the matrix's *"Where DinoMem
  loses / is N/A"* section so a regression-to-DinoMem's-favour is visible.

If a scenario ever adds an LLM-as-judge, the prompt must be published in
`METHODOLOGY.md` and every call logged to `runs/<id>/judgements.jsonl`. Today there
is none — the deterministic assertions are the judge.

## Checks to run before any PR

```bash
python3 -m dinomem_bench --list
python3 tests/test_smoke.py
python3 human_validation/validate.py --check
ruff check .
python3 -m dinomem_bench --sut fake --scenarios all   # full reference run
```

## License

By contributing you agree your contribution is licensed under the repo's
[Apache-2.0](./LICENSE).
