from litex_chess.candidate import apply_candidate
from litex_chess.model import Move, Position


def test_mechanical_e2e4_updates_ep_and_turn():
    position = Position.initial()
    transition = apply_candidate(position, Move.from_uci("e2e4"))
    assert transition.after.piece_at(5, 2) == 0
    assert transition.after.piece_at(5, 4) == 1
    assert transition.after.ep_square == (5, 3)
    assert transition.after.turn == -1


def test_mechanical_castling_moves_rook_without_authorizing_it():
    position = Position.from_fen("4k3/8/8/8/8/8/8/4K2R w K - 0 1")
    transition = apply_candidate(position, Move.from_uci("e1g1"))
    assert transition.is_castle
    assert transition.after.piece_at(7, 1) == 6
    assert transition.after.piece_at(6, 1) == 4
    assert transition.after.castling == ""


def test_mechanical_en_passant_removes_adjacent_pawn():
    position = Position.from_fen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1")
    transition = apply_candidate(position, Move.from_uci("e5d6"))
    assert transition.is_en_passant
    assert transition.after.piece_at(4, 5) == 0
    assert transition.after.piece_at(4, 6) == 1


def test_mechanical_promotion_uses_requested_piece():
    position = Position.from_fen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
    transition = apply_candidate(position, Move.from_uci("a7a8q"))
    assert transition.is_promotion
    assert transition.after.piece_at(1, 8) == 5
