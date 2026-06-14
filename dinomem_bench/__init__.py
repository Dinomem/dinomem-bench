"""dinomem-bench — a reproducible benchmark for multi-agent memory systems.

See DESIGN.md for the methodology. The package is organised as:
  - types       : shared result dataclasses + capability/scope/policy constants
  - adapter     : the SUTAdapter base class every system implements
  - suts/       : adapters (fake reference impl now; real systems later)
  - scenarios/  : S1–S7 deterministic scenario scripts
  - runner      : the run loop + output format (runs/<id>/...)
"""

__version__ = "0.1.0"
