#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient

from litex_chess.api import app


def main() -> int:
    with TestClient(app) as client:
        health = client.get("/api/health")
        health.raise_for_status()
        assert health.json()["gate"]["ready"] is True
        assert health.json()["version"] == "0.8.0"

        index = client.get("/")
        index.raise_for_status()
        assert "Litex Chess Studio" in index.text
        assert "/assets/notation.js" in index.text
        assert "当前形式化代码" in index.text
        assert "formalCodeViewer" in index.text

        formal_source = client.get("/api/formal/source")
        formal_source.raise_for_status()
        formal_payload = formal_source.json()
        assert formal_payload["project_path"] == "formal/chess_rules.lit"
        assert formal_payload["read_only"] is True
        assert formal_payload["line_count"] > 200
        assert "prop sparse_board_transition" in formal_payload["source"]
        assert "prop board_rank_transition" not in formal_payload["source"]
        assert len(formal_payload["sha256"]) == 64

        textbook_page = client.get("/textbook")
        textbook_page.raise_for_status()
        assert "Litex 国际象棋规则教材" in textbook_page.text
        assert "局面实验室" in textbook_page.text
        assert "局面状态实验" in textbook_page.text
        assert "历史状态实验" in textbook_page.text
        assert "status-lab-grid" in textbook_page.text
        assert "history-lab-grid" in textbook_page.text
        assert "endgameLabsSection" in textbook_page.text
        assert "v08_integration" not in textbook_page.text

        textbook_status = client.get("/api/textbook/status")
        textbook_status.raise_for_status()
        textbook_payload = textbook_status.json()
        assert textbook_payload["ready"] is True
        assert textbook_payload["markers_match_catalog"] is True
        assert textbook_payload["mirror"]["in_sync"] is True
        assert textbook_payload["chapter_count"] == 15
        assert textbook_payload["source_module_count"] == 9
        assert textbook_payload["interactive_ready"] is True
        assert textbook_payload["example_count"] == 19
        assert textbook_payload["board_lab_count"] >= 22
        assert textbook_payload["board_move_count"] == 45
        assert textbook_payload["status_lab_count"] == 10
        assert textbook_payload["history_lab_count"] == 5
        assert textbook_payload["endgame_lab_count"] == 5

        endgame_catalog = client.get("/api/textbook/endgames")
        endgame_catalog.raise_for_status()
        lessons = endgame_catalog.json()["lessons"]
        assert {item["lesson_id"] for item in lessons} == {
            "rook-mate-box", "rook-mate-edge", "queen-mate", "knight-dead", "bishop-dead"
        }
        dead_lesson = client.post("/api/textbook/endgames/knight-dead/sessions", json={})
        dead_lesson.raise_for_status()
        dead_payload = dead_lesson.json()
        assert dead_payload["finished"] is True
        assert dead_payload["result"] == "success"
        assert dead_payload["analysis"]["dead_position"]["dead"] is True

        rook_lesson = client.post("/api/textbook/endgames/rook-mate-box/sessions", json={})
        rook_lesson.raise_for_status()
        rook_payload = rook_lesson.json()
        assert rook_payload["finished"] is False
        assert rook_payload["legal_moves"]
        assert rook_payload["workbench_url"].startswith("/?fen=")

        textbook_verify = client.post("/api/textbook/verify", json={})
        textbook_verify.raise_for_status()
        assert textbook_verify.json()["ok"] is True
        assert "定义镜像" in textbook_verify.json()["reason"]

        positive = client.post("/api/textbook/examples/pawn-valid-double", json={})
        positive.raise_for_status()
        assert positive.json()["ok"] is True
        assert positive.json()["observed"] is True

        negative = client.post("/api/textbook/examples/pawn-invalid-blocked-double", json={})
        negative.raise_for_status()
        assert negative.json()["ok"] is True
        assert negative.json()["observed"] is False

        visual_accepted = client.post(
            "/api/textbook/board-labs/lifecycle-e2e4/moves/double",
            json={},
        )
        visual_accepted.raise_for_status()
        accepted_payload = visual_accepted.json()
        assert accepted_payload["ok"] is True
        assert accepted_payload["observed"] is True
        assert accepted_payload["committed_after"]["ep"] == "e3"
        assert accepted_payload["trace"]["board_certificate"]["rank_check_count"] == 0
        assert accepted_payload["trace"]["board_certificate"]["edit_count"] == 2
        assert accepted_payload["trace"]["board_certificate"]["legacy_cell_comparisons"] == 0
        assert accepted_payload["trace"]["board_certificate"]["mismatch_count"] == 0
        assert accepted_payload["trace"]["fen"]["candidate_after"]["ep"] == "e3"
        assert "# [agent-record:start]" in accepted_payload["receipt"]["formal_source"]
        assert "# Certificate SHA seed:" in accepted_payload["receipt"]["formal_source"]

        double_check = client.post(
            "/api/textbook/board-labs/discovered-and-double-check/moves/double",
            json={},
        )
        double_check.raise_for_status()
        double_payload = double_check.json()
        assert double_payload["ok"] is True and double_payload["observed"] is True
        assert double_payload["trace"]["tactical_effects"]["kind"] == "double-check"
        assert double_payload["trace"]["tactical_effects"]["after_checker_count"] == 2

        visual_rejected = client.post(
            "/api/textbook/board-labs/castle-right-absent/moves/short",
            json={},
        )
        visual_rejected.raise_for_status()
        rejected_payload = visual_rejected.json()
        assert rejected_payload["ok"] is True
        assert rejected_payload["observed"] is False
        assert rejected_payload["committed_after"] == rejected_payload["before"]
        assert rejected_payload["trace"]["shape"]["id"] == "white_kingside_castle"

        checkmate = client.post("/api/textbook/status-labs/checkmate-net", json={})
        checkmate.raise_for_status()
        checkmate_payload = checkmate.json()
        assert checkmate_payload["ok"] is True
        assert checkmate_payload["observed_status"] == "checkmate"
        assert checkmate_payload["analysis"]["in_check"] is True
        assert checkmate_payload["analysis"]["legal_move_count"] == 0

        stalemate = client.post("/api/textbook/status-labs/stalemate-net", json={})
        stalemate.raise_for_status()
        stalemate_payload = stalemate.json()
        assert stalemate_payload["ok"] is True
        assert stalemate_payload["observed_status"] == "stalemate"
        assert stalemate_payload["analysis"]["in_check"] is False
        assert stalemate_payload["analysis"]["legal_move_count"] == 0

        threefold = client.post("/api/textbook/history-labs/threefold-cycle", json={})
        threefold.raise_for_status()
        threefold_payload = threefold.json()
        assert threefold_payload["ok"] is True
        assert threefold_payload["result"]["final"]["occurrence"] == 3
        assert threefold_payload["result"]["final"]["threefold_claim_available"] is True
        assert threefold_payload["result"]["final"]["fivefold_automatic"] is False

        endgame_catalog = client.get("/api/textbook/endgames")
        endgame_catalog.raise_for_status()
        lessons = endgame_catalog.json()["lessons"]
        assert {item["lesson_id"] for item in lessons} >= {
            "rook-mate-box", "rook-mate-edge", "queen-mate", "knight-dead"
        }

        dead_lesson = client.post("/api/textbook/endgames/knight-dead/sessions", json={})
        dead_lesson.raise_for_status()
        dead_payload = dead_lesson.json()
        assert dead_payload["finished"] is True
        assert dead_payload["result"] == "success"
        assert dead_payload["analysis"]["dead_position"]["dead"] is True

        endgame_start = client.post("/api/textbook/endgames/rook-mate-edge/sessions", json={})
        endgame_start.raise_for_status()
        endgame_payload = endgame_start.json()
        assert endgame_payload["finished"] is False
        assert endgame_payload["legal_moves"]
        training_id = endgame_payload["training_id"]
        training_move = endgame_payload["legal_moves"][0]
        endgame_play = client.post(
            f"/api/textbook/endgame-sessions/{training_id}/moves",
            json={
                "from": training_move["from"],
                "to": training_move["to"],
                "promotion": training_move.get("promotion"),
            },
        )
        endgame_play.raise_for_status()
        played_payload = endgame_play.json()
        assert played_payload["accepted"] is True
        assert played_payload["history"]
        assert played_payload["last_receipts"]
        assert all("# [agent-record:start]" in row.get("formal_source", "") for row in played_payload["last_receipts"])
        deleted = client.delete(f"/api/textbook/endgame-sessions/{training_id}")
        deleted.raise_for_status()
        assert deleted.json()["deleted"] is True

        created = client.post("/api/sessions", json={})
        created.raise_for_status()
        payload = created.json()
        session_id = payload["session_id"]
        root_id = payload["tree"]["root_id"]

        root_receipt = client.get(f"/api/sessions/{session_id}/nodes/{root_id}/receipt")
        root_receipt.raise_for_status()
        assert root_receipt.json()["receipt"] is None

        e4 = client.post(
            f"/api/sessions/{session_id}/move",
            json={"from": "e2", "to": "e4", "parent_id": root_id},
        )
        e4.raise_for_status()
        assert e4.json()["accepted"] is True
        assert e4.json()["receipt"]["formal_source"]
        e4_tree = e4.json()["tree"]
        e4_node = e4_tree["current_id"]

        stored_receipt = client.get(f"/api/sessions/{session_id}/nodes/{e4_node}/receipt")
        stored_receipt.raise_for_status()
        stored_payload = stored_receipt.json()["receipt"]
        assert stored_payload["accepted"] is True
        assert "by def $pawn_double_move" in stored_payload["formal_source"]

        e5 = client.post(
            f"/api/sessions/{session_id}/move",
            json={"from": "e7", "to": "e5", "parent_id": e4_node},
        )
        e5.raise_for_status()
        assert e5.json()["accepted"] is True

        c5 = client.post(
            f"/api/sessions/{session_id}/move",
            json={"from": "c7", "to": "c5", "parent_id": e4_node},
        )
        c5.raise_for_status()
        assert c5.json()["accepted"] is True
        e4_children = c5.json()["tree"]["nodes"][e4_node]["children"]
        assert len(e4_children) == 2

        exported = client.get(f"/api/sessions/{session_id}/export-pgn")
        exported.raise_for_status()
        assert "1. e4" in exported.text
        assert "(1... c5)" in exported.text or "(1... e5)" in exported.text


        # The exact two-move mate from the reported screenshot must be recorded
        # consistently as SAN '#', result(checkmate), and zero legal replies.
        mate_root = client.post("/api/sessions", json={})
        mate_root.raise_for_status()
        mate_id = mate_root.json()["session_id"]
        mate_parent = mate_root.json()["tree"]["root_id"]
        last = None
        for source, target in (("f2", "f3"), ("e7", "e5"), ("g2", "g4"), ("d8", "h4")):
            last = client.post(
                f"/api/sessions/{mate_id}/move",
                json={"from": source, "to": target, "parent_id": mate_parent},
            )
            last.raise_for_status()
            last_payload = last.json()
            assert last_payload["accepted"] is True
            mate_parent = last_payload["tree"]["current_id"]
        assert last is not None
        mate_payload = last.json()
        assert mate_payload["tree"]["nodes"][mate_parent]["san"] == "Qh4#"
        assert mate_payload["receipt"]["outcome"] == "checkmate"
        assert mate_payload["receipt"]["checker_count"] == 1
        assert mate_payload["receipt"]["legal_reply_count"] == 0
        assert "$result(checkmate)" in mate_payload["receipt"]["agent_source"]
        mate_pgn = client.get(f"/api/sessions/{mate_id}/export-pgn")
        mate_pgn.raise_for_status()
        assert "2. g4 Qh4#" in mate_pgn.text

        imported = client.post(
            "/api/import-pgn",
            json={
                "pgn": (ROOT / "samples" / "nested_variation_demo.pgn").read_text(encoding="utf-8")
            },
        )
        imported.raise_for_status()
        imported_id = imported.json()["session_id"]
        imported_export = client.get(f"/api/sessions/{imported_id}/export-pgn")
        imported_export.raise_for_status()
        assert "(4. Nc3 d6 (4... Bc5" in imported_export.text
        assert imported_export.text.count("(") == 2
        assert "Nf3" in imported_export.text

        print(
            "api_smoke=PASS",
            health.json()["gate"]["engine"],
            session_id,
            imported_id,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
