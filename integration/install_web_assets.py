#!/usr/bin/env python3
"""Install the Litex Chess web extension into a host site's public directory.

This copies only static extension assets. It deliberately does not rewrite the
host router because the production Litex website implementation is not part of
the public golitex repository. Use integration/litex-site/register-chess.js to
register the routes in the host application.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = ROOT / "frontend"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("public_root", type=Path, help="host website public/static root")
    parser.add_argument(
        "--destination",
        default="extensions/chess",
        help="path below public_root (default: extensions/chess)",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    public_root = args.public_root.expanduser().resolve()
    if not public_root.is_dir():
        parser.error(f"public root is not a directory: {public_root}")
    target = (public_root / args.destination).resolve()
    try:
        target.relative_to(public_root)
    except ValueError as exc:
        parser.error("destination must stay inside public_root")
        raise AssertionError from exc

    if target.exists():
        if not args.overwrite:
            parser.error(f"target already exists: {target}; pass --overwrite")
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SOURCE,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    print(target)
    print("Load: /extensions/chess/embed/litex-chess-elements.js")
    print("Register: /extensions/chess/integration/litex-site/register-chess.js")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
