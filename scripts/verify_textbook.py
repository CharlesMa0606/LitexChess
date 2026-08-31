#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from litex_chess.litex_gate import create_gate
from litex_chess.textbook import TextbookRuntime, load_catalog


def main() -> int:
    gate = create_gate(
        ROOT / "formal" / "chess_rules.lit",
        timeout=30.0,
        include_source=True,
    )
    runtime = TextbookRuntime(
        ROOT,
        core_path=ROOT / "formal" / "chess_rules.lit",
        textbook_path=ROOT / "textbook" / "chess_rules_textbook_cn.lit",
        catalog_path=ROOT / "textbook" / "chapters.json",
        gate=gate,
        timeout=60.0,
    )
    try:
        status = runtime.status()
        assert status["ready"] is True, status
        assert status["interactive_ready"] is True, status
        assert status["markers_match_catalog"] is True, status
        assert status["mirror"]["in_sync"] is True, status["mirror"]
        assert status["chapter_count"] == 15, status
        assert status["source_module_count"] == 9, status
        assert status["example_count"] == 19, status
        assert status["board_lab_count"] >= 22, status
        assert status["board_move_count"] == 45, status
        assert status["status_lab_count"] == 10, status
        assert status["history_lab_count"] == 5, status

        complete = runtime.verify_all(force=True)
        assert complete["ok"] is True, complete

        catalog = load_catalog(ROOT / "textbook" / "chapters.json")
        definition_results: list[dict] = []
        board_results: list[dict] = []
        status_results: list[dict] = []
        history_results: list[dict] = []

        for chapter in catalog["chapters"]:
            for example in chapter.get("examples", []):
                result = runtime.verify_example(example["id"])
                assert result["ok"] is True, result
                definition_results.append(
                    {
                        "id": example["id"],
                        "expected": example["expected"],
                        "observed": result["observed"],
                        "elapsed_ms": result["run"]["elapsed_ms"],
                    }
                )

            for lab in chapter.get("board_labs", []):
                for move in lab["moves"]:
                    result = runtime.verify_board_move(lab["id"], move["id"])
                    assert result["ok"] is True, result
                    assert result["trace"]["board_certificate"]["rank_check_count"] == 0
                    assert result["trace"]["board_certificate"]["legacy_cell_comparisons"] == 0
                    if result["observed"]:
                        assert 2 <= result["trace"]["board_certificate"]["edit_count"] <= 4
                        assert result["trace"]["board_certificate"]["exact"] is True
                    assert len(result["trace"]["pipeline"]) == 5
                    assert "tactical_effects" in result["trace"]
                    assert result["receipt"].get("formal_source")
                    if not result["observed"]:
                        assert result["committed_after"] == result["before"]
                    board_results.append(
                        {
                            "lab": lab["id"],
                            "move_id": move["id"],
                            "move": move["uci"],
                            "expected": move["expected"],
                            "observed": result["observed"],
                            "shape": result["trace"]["shape"]["id"],
                            "tactical_kind": result["trace"]["tactical_effects"]["kind"],
                        }
                    )

            for lab in chapter.get("status_labs", []):
                result = runtime.verify_status_lab(lab["id"])
                assert result["ok"] is True, result
                analysis = result["analysis"]
                assert analysis["status"] == lab["expected_status"]
                assert analysis["legal_move_count"] == len(analysis["legal_moves"])
                status_results.append(
                    {
                        "lab": lab["id"],
                        "status": analysis["status"],
                        "in_check": analysis["in_check"],
                        "checker_count": analysis["checker_count"],
                        "candidate_count": analysis["candidate_count"],
                        "legal_move_count": analysis["legal_move_count"],
                        "dead_position": analysis["dead_position"],
                    }
                )

            for lab in chapter.get("history_labs", []):
                result = runtime.verify_history_lab(lab["id"])
                assert result["ok"] is True, result
                assert result["result"]["accepted"] is True
                assert all(result["checks"].values())
                history_results.append(
                    {
                        "lab": lab["id"],
                        "plies": len(result["result"]["timeline"]) - 1,
                        "final": result["result"]["final"],
                    }
                )

        double = next(
            item
            for item in board_results
            if item["lab"] == "discovered-and-double-check" and item["move_id"] == "double"
        )
        discovered = next(
            item
            for item in board_results
            if item["lab"] == "discovered-and-double-check" and item["move_id"] == "discovered"
        )
        assert double["tactical_kind"] == "double-check", double
        assert discovered["tactical_kind"] == "discovered-check", discovered

        payload = {
            "textbook_smoke": "PASS",
            "chapters": status["chapter_count"],
            "source_modules": status["source_module_count"],
            "mirror_code_lines": status["mirror"].get("core_code_lines", status["mirror"].get("core_line_count", status["mirror"].get("core_lines"))),
            "definition_examples": len(definition_results),
            "accepted_definition_examples": sum(item["observed"] for item in definition_results),
            "rejected_definition_examples": sum(not item["observed"] for item in definition_results),
            "board_labs": status["board_lab_count"],
            "board_moves": len(board_results),
            "accepted_board_moves": sum(item["observed"] for item in board_results),
            "rejected_board_moves": sum(not item["observed"] for item in board_results),
            "status_labs": len(status_results),
            "history_labs": len(history_results),
            "definition_results": definition_results,
            "board_results": board_results,
            "status_results": status_results,
            "history_results": history_results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        gate.close()


if __name__ == "__main__":
    raise SystemExit(main())
