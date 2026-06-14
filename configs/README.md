# `configs/` — per-SUT config overrides

A competitor (or anyone reproducing a run) can override the knobs an adapter uses
— model, version, endpoint, index/tuning parameters — **without editing harness
code**, by committing a `configs/<sut>.json` file here.

This is the integrity mechanism behind the benchmark's "competitors are invited to
PR their own adapters / config overrides" promise (see the COI block in
[`../README.md`](../README.md) and [`../CONTRIBUTING.md`](../CONTRIBUTING.md)):
**maintainers keep merge rights on harness code only; your model/version/endpoint
choices are your data, submitted as a config or adapter PR.**

## How it works

`dinomem_bench/config.py` resolves each knob with this precedence (first wins):

```
explicit environment variable   >   configs/<sut>.json value   >   adapter default
```

So a CI run can set an env var; a committed, reproducible profile lives in the
JSON file; and if neither is present the adapter's pinned default applies. Keys
beginning with `_` are treated as comments and ignored.

- `AMBENCH_CONFIG_DIR` overrides the directory (default: this `configs/`).
- `AMBENCH_CONFIG_<SUT>` (e.g. `AMBENCH_CONFIG_PGVECTOR=/path/profile.json`) points
  one SUT at an alternate file — e.g. to A/B two tunings of the same system.

## Which adapters read config today

| SUT | Config keys it reads | Matching env override |
|---|---|---|
| `pgvector` | `embed_model`, `dsn`, `ivfflat_lists` | `PGVECTOR_EMBED_MODEL`, `DATABASE_URL`, `PGVECTOR_IVFFLAT_LISTS` |
| `langmem` | `embed_model` | `LANGMEM_EMBED_MODEL` |

The example files below show the full convention for every hosted/self-host SUT
so a contributor can extend their adapter to read more knobs the same way. Secrets
(API keys) are **never** put in config files — they stay in env vars.

## Submitting an override

1. Edit (or add) `configs/<sut>.json` with your knobs.
2. If your knob isn't read yet, wire it in the adapter via
   `dinomem_bench.config.load("<sut>").get("<key>", <default>, env="<ENV>")`
   (one line; see `suts/pgvector.py` for the worked example).
3. Open a PR. See [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

A config/adapter PR is a data/integration change — maintainers review it for
fairness (black-box, public-API only, pinned versions) but the knob values are
yours.
