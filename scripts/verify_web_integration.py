#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from litex_chess.api import create_app  # noqa: E402


def main() -> int:
    app = create_app()
    with TestClient(app) as client:
        for route in (
            "/textbook/Chess",
            "/textbook/Chess/position-state",
            "/textbook/Chess/certificate-audit",
            "/textbook/Chess/workbench",
            "/playground/chess",
        ):
            response = client.get(route)
            response.raise_for_status()
            assert "litex-site-header" in response.text
            assert "litex-site-sidebar" in response.text
            assert "<iframe" not in response.text.lower()

        entry = client.get("/extensions/chess/embed/litex-chess-elements.js")
        entry.raise_for_status()
        assert "attachShadow" in entry.text
        assert "litex-chess-textbook" in entry.text
        assert "litex-chess-workbench" in entry.text
        assert "iframe" not in entry.text.lower()

        for path in (
            "/extensions/chess/controllers/workbench.js",
            "/extensions/chess/controllers/textbook.js",
            "/extensions/chess/embed/workbench.css",
            "/extensions/chess/embed/textbook.css",
            "/extensions/chess/embed/fragments/workbench.html",
            "/extensions/chess/embed/fragments/textbook.html",
            "/extensions/chess/integration/litex-site/manifest.json",
            "/extensions/chess/integration/litex-site/register-chess.js",
            "/extensions/chess/integration/litex-site/HOST_INTEGRATION_CONTRACT_CN.md",
        ):
            response = client.get(path)
            response.raise_for_status()

        manifest = client.get("/extensions/chess/integration/litex-site/manifest.json").json()
        catalog = client.get("/api/textbook/catalog").json()
        assert manifest["routes"]["base"] == "/textbook/Chess"
        assert manifest["components"]["iframe"] is False
        assert [item["slug"] for item in manifest["chapters"]] == [
            item["slug"] for item in catalog["chapters"]
        ]

        lab = client.get("/api/textbook/board-labs/lifecycle-e2e4")
        lab.raise_for_status()
        assert lab.json()["workbench_url"].startswith("/textbook/Chess/workbench?")
        assert lab.json()["textbook_url"] == "/textbook/Chess/move-pipeline"

        endgames = client.get("/api/textbook/endgames").json()["lessons"]
        assert endgames
        assert all(item["workbench_url"].startswith("/textbook/Chess/workbench?") for item in endgames)

    synced = subprocess.run(
        [sys.executable, "scripts/sync_web_integration.py", "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if synced.returncode != 0:
        print(synced.stdout)
        print(synced.stderr, file=sys.stderr)
        raise SystemExit(synced.returncode)

    # The installer copies assets under a host public root without assuming a
    # private router implementation.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="litex-chess-site-") as temp:
        public_root = Path(temp) / "public"
        public_root.mkdir()
        installed = subprocess.run(
            [sys.executable, "integration/install_web_assets.py", str(public_root)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if installed.returncode != 0:
            print(installed.stdout)
            print(installed.stderr, file=sys.stderr)
            raise SystemExit(installed.returncode)
        target = public_root / "extensions" / "chess"
        assert (target / "embed" / "litex-chess-elements.js").is_file()
        assert (target / "integration" / "litex-site" / "register-chess.js").is_file()

    litex = Path(os.environ.get("LITEX_BIN", ROOT / "tools/litex/linux-amd64/litex"))
    command = [str(litex), "-compact", "-runner", "-r", "integration/golitex-overlay/textbooks/Chess"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=180, check=False)
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise SystemExit(completed.returncode)
    payload = json.loads(completed.stdout)
    assert payload.get("ok") is True

    print("WEB INTEGRATION: PASS")
    print("routes=5 transport=custom-elements+shadow-dom iframe=false native_overlay=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
