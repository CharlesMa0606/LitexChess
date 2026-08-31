from litex_chess.model import Move, Position, START_FEN, square_to_coords, coords_to_square


def test_square_roundtrip():
    for square in ("a1", "e4", "h8"):
        assert coords_to_square(*square_to_coords(square)) == square


def test_start_fen_roundtrip():
    position = Position.from_fen(START_FEN)
    assert position.fen == START_FEN
    assert position.piece_at(5, 1) == 6
    assert position.piece_at(4, 8) == -5


def test_uci_roundtrip():
    assert Move.from_uci("e7e8q").uci == "e7e8q"
