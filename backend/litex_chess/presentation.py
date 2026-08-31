from __future__ import annotations

from .fast_state import analyze_fen
from .litex_gate import Gate
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
    FILES,
)

PIECE_LETTER = {KNIGHT: "N", BISHOP: "B", ROOK: "R", QUEEN: "Q", KING: "K"}
PROMOTION_LETTER = {KNIGHT: "N", BISHOP: "B", ROOK: "R", QUEEN: "Q"}


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _path_clear(position: Position, sf: int, sr: int, tf: int, tr: int) -> bool:
    df = _sign(tf - sf)
    dr = _sign(tr - sr)
    f, r = sf + df, sr + dr
    while (f, r) != (tf, tr):
        if position.piece_at(f, r) != 0:
            return False
        f += df
        r += dr
    return True


def _host_attacks(position: Position, sf: int, sr: int, tf: int, tr: int) -> bool:
    """Presentation-only attack test; never authorizes a move."""
    piece = position.piece_at(sf, sr)
    if piece == 0:
        return False
    side = 1 if piece > 0 else -1
    kind = abs(piece)
    df, dr = tf - sf, tr - sr
    adf, adr = abs(df), abs(dr)
    if kind == PAWN:
        return dr == side and adf == 1
    if kind == KNIGHT:
        return (adf, adr) in {(1, 2), (2, 1)}
    if kind == BISHOP:
        return adf == adr and adf > 0 and _path_clear(position, sf, sr, tf, tr)
    if kind == ROOK:
        return ((df == 0) ^ (dr == 0)) and _path_clear(position, sf, sr, tf, tr)
    if kind == QUEEN:
        geometry = (adf == adr and adf > 0) or ((df == 0) ^ (dr == 0))
        return geometry and _path_clear(position, sf, sr, tf, tr)
    if kind == KING:
        return max(adf, adr) == 1
    return False


def presentation_in_check(position: Position, side: int) -> bool:
    king = 6 * side
    king_square: tuple[int, int] | None = None
    for rank in range(1, 9):
        for file in range(1, 9):
            if position.piece_at(file, rank) == king:
                king_square = (file, rank)
                break
        if king_square:
            break
    if king_square is None:
        return False
    kf, kr = king_square
    for rank in range(1, 9):
        for file in range(1, 9):
            piece = position.piece_at(file, rank)
            if piece * side < 0 and _host_attacks(position, file, rank, kf, kr):
                return True
    return False


def _legal_competitors(
    gate: Gate,
    position: Position,
    transition: CandidateTransition,
) -> list[Move]:
    move = transition.move
    source_kind = abs(transition.source_piece)
    source_side = 1 if transition.source_piece > 0 else -1
    competitors: list[Move] = []
    for rank in range(1, 9):
        for file in range(1, 9):
            if (file, rank) == (move.from_file, move.from_rank):
                continue
            piece = position.piece_at(file, rank)
            if piece != source_side * source_kind:
                continue
            candidate = Move(file, rank, move.to_file, move.to_rank, move.promotion)
            _, receipt = gate.validate_move(position, candidate)
            if receipt.accepted:
                competitors.append(candidate)
    return competitors


def render_san(gate: Gate, transition: CandidateTransition) -> str:
    """Render SAN after Litex accepted the move.

    Disambiguation may ask the Litex gate about same-kind competitors.  The
    terminal suffix comes from the exact cached legal-move generator: ``#``
    for checkmate, ``+`` for nonterminal check, and nothing otherwise.
    """
    move = transition.move
    kind = abs(transition.source_piece)
    if transition.is_castle:
        san = "O-O" if move.to_file == 7 else "O-O-O"
    else:
        capture = transition.is_capture
        target = move.to_square
        if kind == PAWN:
            prefix = FILES[move.from_file - 1] if capture else ""
        else:
            prefix = PIECE_LETTER.get(kind, "?")
            competitors = _legal_competitors(gate, transition.before, transition)
            if competitors:
                same_file = any(other.from_file == move.from_file for other in competitors)
                same_rank = any(other.from_rank == move.from_rank for other in competitors)
                if not same_file:
                    prefix += FILES[move.from_file - 1]
                elif not same_rank:
                    prefix += str(move.from_rank)
                else:
                    prefix += FILES[move.from_file - 1] + str(move.from_rank)
        san = prefix + ("x" if capture else "") + target
        if move.promotion:
            san += "=" + PROMOTION_LETTER[move.promotion]

    try:
        status = str(analyze_fen(transition.after.fen)["status"])
    except Exception:
        # Presentation failure must never alter the Litex acceptance decision.
        status = "check" if presentation_in_check(transition.after, transition.after.turn) else "ongoing"
    if status == "checkmate":
        san += "#"
    elif status == "check":
        san += "+"
    return san
