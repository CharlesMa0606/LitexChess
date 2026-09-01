#!/usr/bin/env python3
"""Copy the native Chess textbook overlay into a local golitex checkout."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "golitex-overlay" / "textbooks" / "Chess"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("golitex_checkout", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    checkout = args.golitex_checkout.expanduser().resolve()
    target = checkout / "textbooks" / "Chess"
    if not (checkout / "textbooks").is_dir():
        parser.error(f"not a golitex checkout: {checkout}")
    if target.exists():
        if not args.overwrite:
            parser.error(f"target already exists: {target}; pass --overwrite")
        shutil.rmtree(target)
    shutil.copytree(SOURCE, target)
    print(target)
    print("Run: target/release/litex -compact -runner -r textbooks/Chess")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
