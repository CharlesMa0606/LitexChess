from __future__ import annotations

from .model import (
    BISHOP,
    KING,
    KNIGHT,
    PAWN,
    QUEEN,
    ROOK,
    CandidateTransition,
    Move,
    Position,
    board_index,
)


def _remove_castling(rights: str, *flags: str) -> str:
    disabled = set(flags)
    return "".join(ch for ch in rights if ch not in disabled)


def apply_candidate(position: Position, move: Move) -> CandidateTransition:
    """Construct one deterministic successor without deciding whether the move is legal.

    The routine intentionally performs no geometric, turn, path, check, or rights validation.
    It merely applies the syntactic transition convention that is then checked by Litex.
    An incorrect host-side guess therefore causes the Litex proposition to fail closed.
    """

    board = list(position.board)
    source_index = board_index(move.from_file, move.from_rank)
    target_index = board_index(move.to_file, move.to_rank)
    source_piece = board[source_index]
    target_piece = board[target_index]
    side = 1 if source_piece > 0 else -1 if source_piece < 0 else position.turn

    is_castle = (
        abs(source_piece) == KING
        and move.from_rank == move.to_rank
        and abs(move.to_file - move.from_file) == 2
    )
    is_en_passant = (
        abs(source_piece) == PAWN
        and move.from_file != move.to_file
        and target_piece == 0
        and position.ep_square == (move.to_file, move.to_rank)
    )
    is_promotion = abs(source_piece) == PAWN and move.to_rank in (1, 8)

    captured_piece = target_piece
    captured_square: tuple[int, int] | None = (
        (move.to_file, move.to_rank) if target_piece else None
    )

    board[source_index] = 0

    if is_en_passant:
        ep_capture_square = (move.to_file, move.from_rank)
        ep_capture_index = board_index(*ep_capture_square)
        captured_piece = board[ep_capture_index]
        captured_square = ep_capture_square
        board[ep_capture_index] = 0

    placed_piece = source_piece
    if is_promotion and move.promotion:
        placed_piece = side * move.promotion
    board[target_index] = placed_piece

    if is_castle:
        rank = move.from_rank
        if move.to_file == 7:
            rook_from, rook_to = 8, 6
        else:
            rook_from, rook_to = 1, 4
        board[board_index(rook_from, rank)] = 0
        board[board_index(rook_to, rank)] = side * ROOK

    rights = position.castling
    if source_piece == KING:
        rights = _remove_castling(rights, "K", "Q")
    elif source_piece == -KING:
        rights = _remove_castling(rights, "k", "q")

    if source_piece == ROOK and (move.from_file, move.from_rank) == (8, 1):
        rights = _remove_castling(rights, "K")
    if source_piece == ROOK and (move.from_file, move.from_rank) == (1, 1):
        rights = _remove_castling(rights, "Q")
    if source_piece == -ROOK and (move.from_file, move.from_rank) == (8, 8):
        rights = _remove_castling(rights, "k")
    if source_piece == -ROOK and (move.from_file, move.from_rank) == (1, 8):
        rights = _remove_castling(rights, "q")

    if target_piece == ROOK and (move.to_file, move.to_rank) == (8, 1):
        rights = _remove_castling(rights, "K")
    if target_piece == ROOK and (move.to_file, move.to_rank) == (1, 1):
        rights = _remove_castling(rights, "Q")
    if target_piece == -ROOK and (move.to_file, move.to_rank) == (8, 8):
        rights = _remove_castling(rights, "k")
    if target_piece == -ROOK and (move.to_file, move.to_rank) == (1, 8):
        rights = _remove_castling(rights, "q")

    ep_square = None
    if abs(source_piece) == PAWN and move.from_file == move.to_file:
        if abs(move.to_rank - move.from_rank) == 2:
            ep_square = (move.from_file, move.from_rank + side)

    halfmove = (
        0
        if abs(source_piece) == PAWN or captured_piece != 0
        else position.halfmove + 1
    )
    fullmove = position.fullmove + (1 if position.turn == -1 else 0)

    after = Position(
        tuple(board),
        turn=-position.turn,
        castling=rights,
        ep_square=ep_square,
        halfmove=halfmove,
        fullmove=fullmove,
    )
    return CandidateTransition(
        before=position,
        move=move,
        after=after,
        source_piece=source_piece,
        target_piece=target_piece,
        captured_piece=captured_piece,
        captured_square=captured_square,
        is_castle=is_castle,
        is_en_passant=is_en_passant,
        is_promotion=is_promotion,
    )
