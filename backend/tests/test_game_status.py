from __future__ import annotations

from pathlib import Path

from litex_chess.game_status import PositionStatusAnalyzer
from litex_chess.model import Position
from litex_chess.query import LitexQueryBuilder

ROOT = Path(__file__).resolve().parents[2]
FORMAL = ROOT / "formal" / "chess_rules.lit"


def analyzer(gate) -> PositionStatusAnalyzer:
    return PositionStatusAnalyzer(gate, LitexQueryBuilder.from_file(FORMAL))


def test_checkmate_and_stalemate_are_distinguished_by_check_state(scripted_gate):
    scripted_gate.accepted_uci = set()
    mate = analyzer(scripted_gate).analyze(
        Position.from_fen("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1")
    )
    stale = analyzer(scripted_gate).analyze(
        Position.from_fen("7k/5Q2/7K/8/8/8/8/8 b - - 0 1")
    )
    assert mate["in_check"] is True and mate["status"] == "checkmate"
    assert stale["in_check"] is False and stale["status"] == "stalemate"
    assert mate["legal_move_count"] == stale["legal_move_count"] == 0


def test_repetition_key_ignores_clocks_but_keeps_castling_rights(scripted_gate):
    a = Position.from_fen("4k2r/8/8/8/8/8/8/4K2R w Kk - 0 1")
    b = Position.from_fen("4k2r/8/8/8/8/8/8/4K2R w Kk - 99 73")
    c = Position.from_fen("4k2r/8/8/8/8/8/8/4K2R w - - 0 1")
    status = analyzer(scripted_gate)
    assert status.repetition_key(a)["key"] == status.repetition_key(b)["key"]
    assert status.repetition_key(a)["key"] != status.repetition_key(c)["key"]


def test_history_distinguishes_threefold_claim_from_fivefold_automatic(scripted_gate):
    cycle = {"g1f3", "g8f6", "f3g1", "f6g8"}
    scripted_gate.accepted_uci = cycle
    start = Position.from_fen("4k1n1/8/8/8/8/8/8/4K1N1 w - - 0 1")
    four_plies = ["g1f3", "g8f6", "f3g1", "f6g8"]
    result = analyzer(scripted_gate).run_history(start, four_plies * 2)
    assert result["accepted"] is True
    assert result["final"]["occurrence"] == 3
    assert result["final"]["threefold_claim_available"] is True
    assert result["final"]["fivefold_automatic"] is False


def test_known_dead_position_is_conservative():
    bare = PositionStatusAnalyzer.known_dead_position(
        Position.from_fen("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    )
    rook = PositionStatusAnalyzer.known_dead_position(
        Position.from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 0 1")
    )
    assert bare == {"known": True, "dead": True, "reason": "仅剩双王，任何合法序列都不可能将死。"}
    assert rook["known"] is False and rook["dead"] is False
