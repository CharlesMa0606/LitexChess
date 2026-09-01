#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def need(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


index_html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
workbench_controller = (ROOT / "frontend/controllers/workbench.js").read_text(encoding="utf-8")
textbook_controller = (ROOT / "frontend/controllers/textbook.js").read_text(encoding="utf-8")
standalone_app = (ROOT / "frontend/app.js").read_text(encoding="utf-8")
standalone_textbook = (ROOT / "frontend/textbook.js").read_text(encoding="utf-8")
site_html = (ROOT / "frontend/site/index.html").read_text(encoding="utf-8")
site_js = (ROOT / "frontend/site/site.js").read_text(encoding="utf-8")
elements_js = (ROOT / "frontend/embed/litex-chess-elements.js").read_text(encoding="utf-8")
workbench_fragment = (ROOT / "frontend/embed/fragments/workbench.html").read_text(encoding="utf-8")
textbook_fragment = (ROOT / "frontend/embed/fragments/textbook.html").read_text(encoding="utf-8")
textbook_css = "".join((ROOT / "frontend/embed/textbook.css").read_text(encoding="utf-8").split())
workbench_css = "".join((ROOT / "frontend/embed/workbench.css").read_text(encoding="utf-8").split())
manifest = json.loads((ROOT / "integration/litex-site/manifest.json").read_text(encoding="utf-8"))
catalog = json.loads((ROOT / "textbook/chapters.json").read_text(encoding="utf-8"))
chapters = catalog["chapters"]

for phrase in ("Agent 走法记录", "完整 Litex 证书", "固定规则内核"):
    need(phrase in index_html, f"standalone workbench missing source tab: {phrase}")
for phrase in ("receiptAgentSource", "formalMode", "/api/formal/source", "resolveWorkbenchContext"):
    need(phrase in workbench_controller, f"workbench controller missing: {phrase}")
for phrase in ("renderEndgameLabs", "startEndgameLesson", "playEndgameMove", "endgameWorkbenchUrl"):
    need(phrase in textbook_controller, f"textbook controller missing: {phrase}")
need("LitexChessWorkbench.mount" in standalone_app, "standalone workbench is not a controller bootstrap")
need("LitexChessTextbook.mount" in standalone_textbook, "standalone textbook is not a controller bootstrap")

# The integrated host owns exactly one global shell; fragments must not carry a
# second app-level header/sidebar and must never use an iframe.
need("litex-site-header" in site_html, "integrated Litex host header missing")
need("litex-site-sidebar" in site_html, "integrated Litex textbook sidebar missing")
need("/textbook/Chess/workbench" in site_html + site_js, "native workbench route missing")
need("<iframe" not in (site_html + workbench_fragment + textbook_fragment + elements_js).lower(), "iframe found in no-iframe integration")
need('customElements.define("litex-chess-textbook"' in elements_js, "textbook custom element missing")
need('customElements.define("litex-chess-workbench"' in elements_js, "workbench custom element missing")
need('static observedAttributes = ["search"]' in elements_js, "workbench does not react to host query changes")
need("attachShadow" in elements_js, "custom elements do not isolate CSS with Shadow DOM")
need(".book-topbar" not in textbook_fragment, "embedded textbook still contains standalone topbar")
need(".book-sidebar" not in textbook_fragment, "embedded textbook still contains standalone sidebar")
need('class="topbar"' not in workbench_fragment, "embedded workbench still contains standalone topbar")
need('class="workspace"' in workbench_fragment, "embedded workbench content missing")
need('class="book-main"' in textbook_fragment, "embedded textbook content missing")
need("root.querySelector" in workbench_controller and "root.querySelector" in textbook_controller, "controllers are not mount-root scoped")

# Square mini boards and responsive embedded workbench.
need("grid-template-columns:repeat(8" in textbook_css, "8 equal mini-board columns missing")
need("grid-template-rows:repeat(8" in textbook_css, "8 equal mini-board rows missing")
need("aspect-ratio:1" in textbook_css, "square mini-board contract missing")
need("@container" in workbench_css, "embedded workbench lacks container-responsive layout")

need(len(chapters) == 15, f"expected 15 chapters, got {len(chapters)}")
need(len(manifest.get("chapters", [])) == 15, "site manifest chapter count differs from curriculum")
need(manifest.get("components", {}).get("iframe") is False, "manifest must explicitly forbid iframe transport")
need(manifest.get("routes", {}).get("base") == "/textbook/Chess", "wrong native route base")
need(any(ch.get("endgame_courses") or ch.get("interactive_endgames") for ch in chapters), "curriculum has no endgame course")

# Native golitex overlay follows the public module textbook convention.
overlay = ROOT / "integration/golitex-overlay/textbooks/Chess"
config = (overlay / "litex.config").read_text(encoding="utf-8")
need("[hierarchy]" in config and "module" in config and "[export]" in config, "native overlay litex.config malformed")
need(len(re.findall(r'^chap\d+\s*=', config, flags=re.M)) == 15, "native overlay must export 15 chapter modules")
need((overlay / "chess_rules.lit").is_file(), "native overlay rule module missing")
need(all((overlay / f"chapter{int(ch['number']):02d}-{ch['slug']}.lit").is_file() for ch in chapters), "native overlay chapter files missing")
need((ROOT / "integration/litex-site/HOST_INTEGRATION_CONTRACT_CN.md").is_file(), "host integration contract missing")
need((ROOT / "integration/install_web_assets.py").is_file(), "static asset installer missing")

if errors:
    print("FRONTEND / SITE INTEGRATION CONTRACT: FAIL")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("FRONTEND / SITE INTEGRATION CONTRACT: PASS")
print("transport=custom-elements+shadow-dom iframe=false routes=/textbook/Chess/*")
