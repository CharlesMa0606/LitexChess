#!/usr/bin/env python3
"""Generate or verify the release source manifest.

The manifest covers every packaged regular file except itself and disposable
runtime caches.  Paths are relative POSIX paths and are sorted bytewise so the
result is stable across platforms.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "SOURCE_MANIFEST.sha256"


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if rel == Path("SOURCE_MANIFEST.sha256"):
        return False
    if any(part in {".git", ".venv", ".local", ".pytest_cache", "__pycache__"} for part in parts):
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    if rel.parts[:2] == ("verification", "generated") and path.name.startswith("."):
        return False
    return path.is_file()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def render() -> str:
    paths = sorted(
        (path for path in ROOT.rglob("*") if included(path)),
        key=lambda path: path.relative_to(ROOT).as_posix().encode("utf-8"),
    )
    return "".join(
        f"{digest(path)}  {path.relative_to(ROOT).as_posix()}\n"
        for path in paths
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not MANIFEST.is_file():
            print("manifest=FAIL missing SOURCE_MANIFEST.sha256")
            return 1
        actual = MANIFEST.read_text(encoding="utf-8")
        if actual != expected:
            print("manifest=FAIL content or file set differs")
            return 1
        print(f"manifest=PASS files={expected.count(chr(10))}")
        return 0
    MANIFEST.write_text(expected, encoding="utf-8")
    print(f"manifest=WRITTEN files={expected.count(chr(10))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
