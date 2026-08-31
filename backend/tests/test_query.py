from pathlib import Path
import re

from litex_chess.candidate import apply_candidate
from litex_chess.model import Move, Position
from litex_chess.query import LitexQueryBuilder

ROOT = Path(__file__).resolve().parents[2]


def test_agent_record_is_part_of_actual_query_transaction():
    builder = LitexQueryBuilder.from_file(ROOT / "formal" / "chess_rules.lit")
    transition = apply_candidate(Position.initial(), Move.from_uci("e2e4"))
    query = builder.build_move_query(transition)
    for token in (
        "# [agent-record:start]",
        "by def $move(e2, e4)",
        "by def $promotion_choice(0)",
        "by def $result(ongoing)",
        "# [agent-record:end]",
    ):
        assert token in query.source
    assert query.agent_source in query.source


def test_runtime_kernel_defines_agent_protocol():
    source = (ROOT / "formal" / "chess_rules.lit").read_text(encoding="utf-8")
    assert re.search(r"(?m)^prop\s+move\s*\(", source)
    assert re.search(r"(?m)^prop\s+promotion_choice\s*\(", source)
    assert re.search(r"(?m)^prop\s+result\s*\(", source)
    assert re.search(r"(?m)^prop\s+result_witness\s*\(", source)


def test_sparse_transition_is_the_production_board_contract():
    source = (ROOT / "backend" / "litex_chess" / "query.py").read_text(encoding="utf-8")
    assert "sparse_board_transition" in (ROOT / "formal" / "chess_rules.lit").read_text(encoding="utf-8")
    assert "sparse_litex_lines" in source
    assert "board_transition_mode: str = \"sparse\"" in source
