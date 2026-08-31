from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

FILES = "abcdefgh"
RANKS = "12345678"

EMPTY = 0
PAWN = 1
KNIGHT = 2
BISHOP = 3
ROOK = 4
QUEEN = 5
KING = 6

PIECE_TO_FEN = {
    1: "P", 2: "N", 3: "B", 4: "R", 5: "Q", 6: "K",
    -1: "p", -2: "n", -3: "b", -4: "r", -5: "q", -6: "k",
}
FEN_TO_PIECE = {v: k for k, v in PIECE_TO_FEN.items()}
PROMOTION_TO_CODE = {"n": KNIGHT, "b": BISHOP, "r": ROOK, "q": QUEEN}
CODE_TO_PROMOTION = {v: k for k, v in PROMOTION_TO_CODE.items()}

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class PositionFormatError(ValueError):
    """Raised when a FEN or square is structurally malformed."""


def square_to_coords(square: str) -> tuple[int, int]:
    if len(square) != 2 or square[0] not in FILES or square[1] not in RANKS:
        raise PositionFormatError(f"invalid square: {square!r}")
    return FILES.index(square[0]) + 1, int(square[1])


def coords_to_square(file: int, rank: int) -> str:
    if not (1 <= file <= 8 and 1 <= rank <= 8):
        raise PositionFormatError(f"invalid coordinates: {(file, rank)!r}")
    return f"{FILES[file - 1]}{rank}"


def board_index(file: int, rank: int) -> int:
    if not (1 <= file <= 8 and 1 <= rank <= 8):
        raise PositionFormatError(f"invalid coordinates: {(file, rank)!r}")
    return (rank - 1) * 8 + (file - 1)


@dataclass(frozen=True, slots=True)
class Move:
    from_file: int
    from_rank: int
    to_file: int
    to_rank: int
    promotion: int = 0

    def __post_init__(self) -> None:
        coords_to_square(self.from_file, self.from_rank)
        coords_to_square(self.to_file, self.to_rank)
        if self.promotion not in (0, KNIGHT, BISHOP, ROOK, QUEEN):
            raise PositionFormatError(
                "promotion must be 0, knight(2), bishop(3), rook(4), or queen(5)"
            )

    @classmethod
    def from_uci(cls, uci: str) -> "Move":
        text = uci.strip().lower()
        if len(text) not in (4, 5):
            raise PositionFormatError(f"invalid UCI move: {uci!r}")
        ff, fr = square_to_coords(text[:2])
        tf, tr = square_to_coords(text[2:4])
        promotion = 0
        if len(text) == 5:
            try:
                promotion = PROMOTION_TO_CODE[text[4]]
            except KeyError as exc:
                raise PositionFormatError(f"invalid promotion in UCI move: {uci!r}") from exc
        return cls(ff, fr, tf, tr, promotion)

    @property
    def from_square(self) -> str:
        return coords_to_square(self.from_file, self.from_rank)

    @property
    def to_square(self) -> str:
        return coords_to_square(self.to_file, self.to_rank)

    @property
    def uci(self) -> str:
        suffix = CODE_TO_PROMOTION.get(self.promotion, "")
        return f"{self.from_square}{self.to_square}{suffix}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_square,
            "to": self.to_square,
            "promotion": CODE_TO_PROMOTION.get(self.promotion),
            "uci": self.uci,
        }


@dataclass(frozen=True, slots=True)
class Position:
    board: tuple[int, ...]
    turn: int = 1
    castling: str = "KQkq"
    ep_square: tuple[int, int] | None = None
    halfmove: int = 0
    fullmove: int = 1

    def __post_init__(self) -> None:
        if len(self.board) != 64:
            raise PositionFormatError("board must contain exactly 64 squares")
        if any(piece not in range(-6, 7) for piece in self.board):
            raise PositionFormatError("piece codes must lie in [-6, 6]")
        if self.turn not in (1, -1):
            raise PositionFormatError("turn must be +1 (white) or -1 (black)")
        normalized = "".join(ch for ch in "KQkq" if ch in self.castling)
        if normalized != self.castling or len(set(self.castling)) != len(self.castling):
            raise PositionFormatError("castling rights must be an ordered subset of KQkq")
        if self.ep_square is not None:
            f, r = self.ep_square
            coords_to_square(f, r)
            if r not in (3, 6):
                raise PositionFormatError("FEN en-passant target must lie on rank 3 or 6")
        if self.halfmove < 0:
            raise PositionFormatError("halfmove must be nonnegative")
        if self.fullmove < 1:
            raise PositionFormatError("fullmove must be positive")

    @classmethod
    def initial(cls) -> "Position":
        return cls.from_fen(START_FEN)

    @classmethod
    def from_fen(cls, fen: str) -> "Position":
        parts = fen.strip().split()
        if len(parts) != 6:
            raise PositionFormatError("FEN must have six fields")
        placement, active, castling, ep, halfmove, fullmove = parts
        rank_tokens = placement.split("/")
        if len(rank_tokens) != 8:
            raise PositionFormatError("FEN placement must have eight ranks")
        board = [0] * 64
        for fen_rank_index, token in enumerate(rank_tokens):
            rank = 8 - fen_rank_index
            file = 1
            for char in token:
                if char.isdigit():
                    gap = int(char)
                    if not 1 <= gap <= 8:
                        raise PositionFormatError(f"invalid FEN digit: {char}")
                    file += gap
                    continue
                if char not in FEN_TO_PIECE:
                    raise PositionFormatError(f"invalid FEN piece: {char}")
                if file > 8:
                    raise PositionFormatError("too many files in FEN rank")
                board[board_index(file, rank)] = FEN_TO_PIECE[char]
                file += 1
            if file != 9:
                raise PositionFormatError("each FEN rank must describe exactly eight files")
        if active not in ("w", "b"):
            raise PositionFormatError("active color must be w or b")
        castling_rights = "" if castling == "-" else castling
        ep_square = None if ep == "-" else square_to_coords(ep)
        try:
            halfmove_int = int(halfmove)
            fullmove_int = int(fullmove)
        except ValueError as exc:
            raise PositionFormatError("FEN clocks must be integers") from exc
        return cls(
            tuple(board),
            1 if active == "w" else -1,
            castling_rights,
            ep_square,
            halfmove_int,
            fullmove_int,
        )

    def piece_at(self, file: int, rank: int) -> int:
        return self.board[board_index(file, rank)]

    def with_board(self, values: Iterable[int], **changes: Any) -> "Position":
        payload = {
            "board": tuple(values),
            "turn": self.turn,
            "castling": self.castling,
            "ep_square": self.ep_square,
            "halfmove": self.halfmove,
            "fullmove": self.fullmove,
        }
        payload.update(changes)
        return Position(**payload)

    @property
    def fen(self) -> str:
        rank_strings: list[str] = []
        for rank in range(8, 0, -1):
            run = 0
            chunks: list[str] = []
            for file in range(1, 9):
                piece = self.piece_at(file, rank)
                if piece == 0:
                    run += 1
                    continue
                if run:
                    chunks.append(str(run))
                    run = 0
                chunks.append(PIECE_TO_FEN[piece])
            if run:
                chunks.append(str(run))
            rank_strings.append("".join(chunks))
        placement = "/".join(rank_strings)
        active = "w" if self.turn == 1 else "b"
        castling = self.castling or "-"
        ep = "-" if self.ep_square is None else coords_to_square(*self.ep_square)
        return f"{placement} {active} {castling} {ep} {self.halfmove} {self.fullmove}"

    def to_dict(self) -> dict[str, Any]:
        pieces: dict[str, int] = {}
        for rank in range(1, 9):
            for file in range(1, 9):
                piece = self.piece_at(file, rank)
                if piece:
                    pieces[coords_to_square(file, rank)] = piece
        return {
            "fen": self.fen,
            "turn": "white" if self.turn == 1 else "black",
            "castling": self.castling or "-",
            "ep": None if self.ep_square is None else coords_to_square(*self.ep_square),
            "halfmove": self.halfmove,
            "fullmove": self.fullmove,
            "pieces": pieces,
        }


@dataclass(frozen=True, slots=True)
class CandidateTransition:
    before: Position
    move: Move
    after: Position
    source_piece: int
    target_piece: int
    captured_piece: int
    captured_square: tuple[int, int] | None
    is_castle: bool
    is_en_passant: bool
    is_promotion: bool

    @property
    def is_capture(self) -> bool:
        return self.captured_piece != 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "move": self.move.to_dict(),
            "before_fen": self.before.fen,
            "after_fen": self.after.fen,
            "source_piece": self.source_piece,
            "target_piece": self.target_piece,
            "captured_piece": self.captured_piece,
            "captured_square": (
                None if self.captured_square is None else coords_to_square(*self.captured_square)
            ),
            "is_castle": self.is_castle,
            "is_en_passant": self.is_en_passant,
            "is_promotion": self.is_promotion,
        }


@dataclass(slots=True)
class GateReceipt:
    accepted: bool
    engine: str
    query_sha256: str
    elapsed_ms: float
    reason: str
    results: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    formal_source: str | None = None
    agent_source: str | None = None
    query_kind: str | None = None
    board_transition_mode: str | None = None
    outcome: str | None = None
    checker_count: int | None = None
    legal_reply_count: int | None = None

    def to_dict(self, include_source: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "accepted": self.accepted,
            "engine": self.engine,
            "query_sha256": self.query_sha256,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "reason": self.reason,
            "results": self.results,
            "diagnostics": self.diagnostics,
            "query_kind": self.query_kind,
            "board_transition_mode": self.board_transition_mode,
            "outcome": self.outcome,
            "checker_count": self.checker_count,
            "legal_reply_count": self.legal_reply_count,
        }
        if include_source:
            payload["agent_source"] = self.agent_source
            payload["formal_source"] = self.formal_source
        return payload
