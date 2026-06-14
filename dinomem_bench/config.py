"""SUT config override loader (stdlib-only).

A competitor — or anyone reproducing a run — can override the knobs an adapter
uses (model, version, endpoint, top_k, …) WITHOUT touching harness code, by either:

  1. setting an environment variable, or
  2. committing a JSON file under ``configs/<sut>.json`` and pointing the harness
     at the directory (``AMBENCH_CONFIG_DIR``, default ``configs/`` at the repo
     root), or selecting a non-default profile file with ``AMBENCH_CONFIG_<SUT>``.

Resolution order for a single knob (first non-None wins):

    explicit env var  >  configs/<sut>.json value  >  adapter default

This is intentionally tiny and dependency-free: a config file is plain JSON
(stdlib ``json``), so it carries no new runtime dep and stays inside the
"stdlib-only core" guarantee.

See ``CONTRIBUTING.md`` for the PR convention (maintainers keep merge rights on
harness code only; a config/adapter PR is a data/integration change, not harness).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _config_dir() -> Path:
    return Path(os.environ.get("AMBENCH_CONFIG_DIR") or (_REPO_ROOT / "configs"))


def _config_path(sut: str) -> Path:
    """Per-SUT override file. ``AMBENCH_CONFIG_<SUT>`` selects an alternate file
    (e.g. a competitor's tuned profile); otherwise ``configs/<sut>.json``."""
    override = os.environ.get(f"AMBENCH_CONFIG_{sut.upper()}")
    if override:
        return Path(override)
    return _config_dir() / f"{sut}.json"


class SUTConfig:
    """Resolved config for one SUT. Look up a knob with ``get`` (env > file >
    default). Construct via :func:`load`."""

    def __init__(self, sut: str, data: dict[str, Any], source: str | None) -> None:
        self.sut = sut
        self._data = data or {}
        self.source = source  # path the file values came from, or None

    def get(self, key: str, default: Any = None, *, env: str | None = None) -> Any:
        """Resolve one knob. ``env`` names an environment variable that, if set,
        takes priority over the config file (the documented override order)."""
        if env and os.environ.get(env) not in (None, ""):
            return os.environ[env]
        if key in self._data and self._data[key] is not None:
            return self._data[key]
        return default

    def get_int(self, key: str, default: int, *, env: str | None = None) -> int:
        v = self.get(key, default, env=env)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SUTConfig({self.sut!r}, keys={sorted(self._data)}, source={self.source!r})"


def load(sut: str) -> SUTConfig:
    """Load ``configs/<sut>.json`` if present (ignoring keys that start with ``_``,
    which are documentation/comments). Missing file -> empty config (adapter
    defaults apply). Malformed JSON raises, so a broken override fails loud."""
    path = _config_path(sut)
    if not path.exists():
        return SUTConfig(sut, {}, None)
    raw = json.loads(path.read_text())
    data = {k: v for k, v in raw.items() if not k.startswith("_")}
    return SUTConfig(sut, data, str(path))
