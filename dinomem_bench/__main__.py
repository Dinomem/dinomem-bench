"""CLI entry point.

    python -m dinomem_bench --sut all --scenarios all
    python -m dinomem_bench --sut fake --scenarios s1,s4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, scenarios as scn
from .suts import available


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="dinomem-bench",
        description="Reproducible multi-agent memory benchmark (S1–S7).",
    )
    p.add_argument("--sut", default="all",
                   help="SUT name, comma list, or 'all'. Available: " + ", ".join(available()))
    p.add_argument("--scenarios", default="all",
                   help="'all' or comma list of ids/slugs, e.g. 's1,s4'.")
    p.add_argument("--out", default="runs", help="output root dir (default: runs/)")
    p.add_argument("--list", action="store_true", help="list SUTs + scenarios and exit")
    p.add_argument("--version", action="version", version=f"dinomem-bench {__version__}")
    args = p.parse_args(argv)

    if args.list:
        print("SUTs:      " + ", ".join(available()))
        print("Scenarios: " + ", ".join(f"{s.id}:{s.slug}" for s in scn.ALL))
        return 0

    # resolve SUTs
    if args.sut.strip().lower() == "all":
        sut_names = available()
    else:
        sut_names = [s.strip() for s in args.sut.split(",") if s.strip()]
        unknown = [s for s in sut_names if s not in available()]
        if unknown:
            p.error(f"unknown SUT(s): {', '.join(unknown)}. Available: {', '.join(available())}")

    try:
        selected = scn.select(args.scenarios)
    except KeyError as e:
        p.error(str(e))

    # late import so --list/--help don't pay for it
    from .runner import run

    print(f"dinomem-bench {__version__}")
    print(f"SUTs:      {', '.join(sut_names)}")
    print(f"Scenarios: {', '.join(s.id for s in selected)}")
    run_dir = run(sut_names, selected, Path(args.out))
    print(f"\n✔ wrote {run_dir}")
    print(f"  summary: {run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
