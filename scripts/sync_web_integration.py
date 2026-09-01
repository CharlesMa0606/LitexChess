#!/usr/bin/env python3
"""Generate Litex-site and native-book manifests from the canonical catalog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "textbook" / "chapters.json"
SITE_MANIFEST = ROOT / "integration" / "litex-site" / "manifest.json"
SITE_MANIFEST_PUBLIC = ROOT / "frontend" / "integration" / "litex-site" / "manifest.json"
OVERLAY = ROOT / "integration" / "golitex-overlay" / "textbooks" / "Chess"
BOOK_EXTENSION = OVERLAY / "book.extension.json"
BOOK_CONFIG = OVERLAY / "litex.config"
TESTED_COMMIT = "2e457026928e009344d35f363e721c2540c410b6"


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def chapter_rows(catalog: dict) -> list[dict]:
    rows = []
    for chapter in catalog["chapters"]:
        number = int(chapter["number"])
        slug = chapter["slug"]
        rows.append(
            {
                "number": number,
                "slug": slug,
                "title": chapter["title"],
                "part": chapter.get("part"),
                "part_title": chapter.get("part_title"),
                "route": f"/textbook/Chess/{slug}",
                "file": f"chapter{number:02d}-{slug}.lit",
            }
        )
    return rows


def render_site_manifest(catalog: dict, rows: list[dict]) -> str:
    data = {
        "schema_version": 1,
        "id": "Chess",
        "title": "International Chess Rules and Formal Verification",
        "title_zh": catalog.get("title", "国际象棋规则与形式化验证"),
        "language": "zh-CN",
        "upstream": {
            "repository": "litexlang/golitex",
            "tested_commit": TESTED_COMMIT,
            "textbook_directory": "textbooks/Chess",
        },
        "routes": {
            "base": "/textbook/Chess",
            "default": "/textbook/Chess/position-state",
            "workbench": "/textbook/Chess/workbench",
            "playground_alias": "/playground/chess",
        },
        "assets": {
            "entry": "/extensions/chess/embed/litex-chess-elements.js",
            "root": "/extensions/chess/",
            "source_base": "/textbook-source",
            "api_base": "/api",
        },
        "components": {
            "chapter": "litex-chess-textbook",
            "workbench": "litex-chess-workbench",
            "transport": "shadow-dom-web-components",
            "iframe": False,
        },
        "integration": {
            "host_contract": "/extensions/chess/integration/litex-site/HOST_INTEGRATION_CONTRACT_CN.md",
            "route_adapter": "/extensions/chess/integration/litex-site/register-chess.js",
            "requires_single_host_shell": True,
            "iframe": False,
        },
        "chapters": [
            {key: row[key] for key in ("number", "slug", "title", "part", "part_title", "route")}
            for row in rows
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_book_extension(catalog: dict, rows: list[dict]) -> str:
    data = {
        "id": "Chess",
        "title": "International Chess Rules",
        "title_zh": catalog.get("title", "国际象棋规则与形式化验证"),
        "language": "zh-CN",
        "default_chapter": rows[0]["slug"],
        "interactive_element": "litex-chess-textbook",
        "workbench_element": "litex-chess-workbench",
        "route_base": "/textbook/Chess",
        "chapters": [
            {key: row[key] for key in ("number", "slug", "title", "file", "route")}
            for row in rows
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def render_config(rows: list[dict]) -> str:
    lines = ["[hierarchy]", "module", "", "[export]", 'rules = "./chess_rules.lit"']
    lines.extend(f'chap{row["number"]} = "./{row["file"]}"' for row in rows)
    return "\n".join(lines) + "\n"


def expected_files() -> dict[Path, str]:
    catalog = load_catalog()
    rows = chapter_rows(catalog)
    missing = [row["file"] for row in rows if not (OVERLAY / row["file"]).is_file()]
    if missing:
        raise FileNotFoundError("missing native chapter files: " + ", ".join(missing))
    site = render_site_manifest(catalog, rows)
    return {
        SITE_MANIFEST: site,
        SITE_MANIFEST_PUBLIC: site,
        BOOK_EXTENSION: render_book_extension(catalog, rows),
        BOOK_CONFIG: render_config(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = expected_files()
    stale = [path for path, content in files.items() if not path.is_file() or path.read_text(encoding="utf-8") != content]
    if args.check:
        if stale:
            print("integration_manifests=STALE")
            for path in stale:
                print(path.relative_to(ROOT))
            return 1
        print(f"integration_manifests=SYNC chapters={len(load_catalog()['chapters'])}")
        return 0
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
