from __future__ import annotations

from litex_chess.compact_transition import compact_query_source

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


def legacy_source() -> str:
    rows = "\n".join(
        "by def $chess_rules::board_rank_transition(" + ",".join(["0"] * 16) + ")"
        for _ in range(8)
    )
    return f"# before_fen: {START}\n# after_fen: {AFTER}\n{rows}\n"


def test_compact_query_is_non_recursive_and_omits_rank_audit() -> None:
    output = compact_query_source(legacy_source(), mode="compact")
    assert "board_rank_transition" not in output
    assert "sparse_board_transition" in output
    assert "sparse_square_edit" in output


def test_compact_transform_is_idempotent() -> None:
    once = compact_query_source(legacy_source(), mode="compact")
    twice = compact_query_source(once, mode="compact")
    assert once == twice


def test_dual_keeps_legacy_audit_as_optional_differential_check() -> None:
    output = compact_query_source(legacy_source(), mode="dual")
    assert "sparse_board_transition" in output
    assert output.count("board_rank_transition") == 8


def test_legacy_mode_remains_available_for_archived_reproduction() -> None:
    output = compact_query_source(legacy_source(), mode="legacy")
    assert output.count("board_rank_transition") == 8
