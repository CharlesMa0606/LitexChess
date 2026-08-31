from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .agent_record import make_agent_record
from .compact_transition import sparse_litex_lines
from .fast_state import analyze_fen
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


@dataclass(frozen=True, slots=True)
class BuiltQuery:
    source: str
    sha256: str
    kind: str
    agent_source: str = ""
    board_transition_mode: str = "sparse"
    outcome: str | None = None
    checker_count: int | None = None
    legal_reply_count: int | None = None


class LitexQueryBuilder:
    """Compile one concrete chess edge into a finite Litex certificate.

    ``formal/chess_rules.lit`` supplies fixed predicates.  Each query presents
    literal board/state data, one selected movement predicate, a canonical sparse
    successor delta guarded by an injective board code, metadata equality, and finite
    king-safety counts.  Every statement must be accepted by Litex.

    The deterministic certificate compiler is intentionally inspectable and is
    part of the documented trusted boundary.  It is not a second chess engine
    and there is no non-Litex acceptance fallback.
    """

    def __init__(self, formal_source: str) -> None:
        self.formal_source = formal_source.rstrip() + "\n"
        self.board_transition_mode = "sparse"

    @classmethod
    def from_file(cls, path: str | Path) -> "LitexQueryBuilder":
        return cls(Path(path).read_text(encoding="utf-8"))

    @staticmethod
    def _digest(source: str) -> str:
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @staticmethod
    def _sign(value: int) -> int:
        return (value > 0) - (value < 0)

    @staticmethod
    def _board_comment(label: str, position: Position) -> str:
        # FEN already serializes the complete Position.  The detailed query then
        # lists only the 2--4 changed squares, avoiding sixteen repeated rank rows.
        return f"# {label} FEN: {position.fen}"

    @classmethod
    def _squares_between(
        cls, sf: int, sr: int, tf: int, tr: int
    ) -> list[tuple[int, int]]:
        df, dr = tf - sf, tr - sr
        aligned = df == 0 or dr == 0 or abs(df) == abs(dr)
        if not aligned or (df == 0 and dr == 0):
            return []
        step_f, step_r = cls._sign(df), cls._sign(dr)
        result: list[tuple[int, int]] = []
        file, rank = sf + step_f, sr + step_r
        while (file, rank) != (tf, tr):
            if not (1 <= file <= 8 and 1 <= rank <= 8):
                return []
            result.append((file, rank))
            file += step_f
            rank += step_r
        return result

    @classmethod
    def _path_blockers(
        cls, position: Position, sf: int, sr: int, tf: int, tr: int
    ) -> list[tuple[int, int]]:
        return [
            square
            for square in cls._squares_between(sf, sr, tf, tr)
            if position.piece_at(*square) != 0
        ]

    @staticmethod
    def _rights(position: Position) -> dict[str, int]:
        return {key: int(key in position.castling) for key in "KQkq"}

    @staticmethod
    def _king_count(position: Position, side: int) -> int:
        return sum(piece == KING * side for piece in position.board)

    @staticmethod
    def _last_rank_pawn_count(position: Position) -> int:
        return sum(
            abs(position.piece_at(file, rank)) == PAWN
            for file in range(1, 9)
            for rank in (1, 8)
        )

    @staticmethod
    def _find_king(position: Position, side: int) -> tuple[int, int]:
        target = KING * side
        for file in range(1, 9):
            for rank in range(1, 9):
                if position.piece_at(file, rank) == target:
                    return file, rank
        # The king-count certificate fails in this case; concrete coordinates
        # keep the generated query syntactically total.
        return 1, 1

    @classmethod
    def _piece_attacks(
        cls,
        position: Position,
        piece: int,
        sf: int,
        sr: int,
        tf: int,
        tr: int,
    ) -> bool:
        if piece == 0 or (sf, sr) == (tf, tr):
            return False
        side = cls._sign(piece)
        kind = abs(piece)
        df, dr = tf - sf, tr - sr
        if kind == PAWN:
            return dr == side and abs(df) == 1
        if kind == KNIGHT:
            return (abs(df), abs(dr)) in {(1, 2), (2, 1)}
        if kind == KING:
            return max(abs(df), abs(dr)) == 1

        diagonal = abs(df) == abs(dr) and df != 0
        orthogonal = (df == 0) != (dr == 0)
        if kind == BISHOP and not diagonal:
            return False
        if kind == ROOK and not orthogonal:
            return False
        if kind == QUEEN and not (diagonal or orthogonal):
            return False
        if kind not in (BISHOP, ROOK, QUEEN):
            return False
        return not cls._path_blockers(position, sf, sr, tf, tr)

    @classmethod
    def _unsafe_count(
        cls, position: Position, king_side: int
    ) -> tuple[int, tuple[int, int]]:
        king_square = cls._find_king(position, king_side)
        attacker_side = -king_side
        tf, tr = king_square
        count = 0
        for sf in range(1, 9):
            for sr in range(1, 9):
                piece = position.piece_at(sf, sr)
                if cls._sign(piece) != attacker_side:
                    continue
                count += int(cls._piece_attacks(position, piece, sf, sr, tf, tr))
        return count, king_square

    @staticmethod
    def _king_step_position(position: Position, move: Move) -> Position:
        board = list(position.board)
        source = position.piece_at(move.from_file, move.from_rank)
        step_file = move.from_file + (1 if move.to_file > move.from_file else -1)
        board[board_index(move.from_file, move.from_rank)] = 0
        board[board_index(step_file, move.from_rank)] = source
        return Position(
            tuple(board),
            turn=position.turn,
            castling=position.castling,
            ep_square=position.ep_square,
            halfmove=position.halfmove,
            fullmove=position.fullmove,
        )

    @staticmethod
    def _select_shape(transition: CandidateTransition) -> str:
        p, m = transition.before, transition.move
        source = p.piece_at(m.from_file, m.from_rank)
        target = p.piece_at(m.to_file, m.to_rank)
        kind = abs(source)
        df = m.to_file - m.from_file
        dr = m.to_rank - m.from_rank

        if kind == KING and m.from_rank == m.to_rank and abs(df) == 2:
            if p.turn == 1:
                return (
                    "white_kingside_castle"
                    if df > 0
                    else "white_queenside_castle"
                )
            return "black_kingside_castle" if df > 0 else "black_queenside_castle"

        if kind == PAWN:
            if m.promotion != 0 or m.to_rank in (1, 8):
                return "pawn_promotion"
            if target == 0 and df != 0 and p.ep_square == (m.to_file, m.to_rank):
                return "en_passant_move"
            if target != 0 or df != 0:
                return "pawn_capture"
            if abs(dr) == 2:
                return "pawn_double_move"
            return "pawn_single_move"

        return {
            KNIGHT: "knight_move",
            BISHOP: "bishop_move",
            ROOK: "rook_move",
            QUEEN: "queen_move",
            KING: "king_step",
        }.get(kind, "king_step")

    @classmethod
    def _shape_certificate(
        cls,
        transition: CandidateTransition,
        shape: str,
        castle_safety: tuple[int, int, int],
    ) -> list[str]:
        p, m = transition.before, transition.move
        side = p.turn
        source = p.piece_at(m.from_file, m.from_rank)
        target = p.piece_at(m.to_file, m.to_rank)
        blockers = cls._path_blockers(
            p, m.from_file, m.from_rank, m.to_file, m.to_rank
        )
        path_text = ", ".join(f"({f},{r})" for f, r in cls._squares_between(
            m.from_file, m.from_rank, m.to_file, m.to_rank
        )) or "none"
        lines = [
            f"# Selected movement certificate: {shape}",
            f"# Geometric path squares: {path_text}",
            f"by def $path_clear({len(blockers)})",
        ]

        common = (
            f"{source}, {target}, {side}, {m.from_file}, {m.from_rank}, "
            f"{m.to_file}, {m.to_rank}"
        )
        if shape == "pawn_single_move":
            lines.append(f"by def $pawn_single_move({common}, {m.promotion})")
        elif shape == "pawn_double_move":
            middle_rank = m.from_rank + side
            middle = (
                p.piece_at(m.from_file, middle_rank)
                if 1 <= middle_rank <= 8
                else 99
            )
            lines.append(
                f"by def $pawn_double_move({source}, {target}, {middle}, {side}, "
                f"{m.from_file}, {m.from_rank}, {m.to_file}, {m.to_rank}, {m.promotion})"
            )
        elif shape == "pawn_capture":
            lines.append(f"by def $pawn_capture({common}, {m.promotion})")
        elif shape == "pawn_promotion":
            lines.append(f"by def $pawn_promotion({common}, {m.promotion})")
        elif shape == "en_passant_move":
            captured = p.piece_at(m.to_file, m.from_rank)
            ep_file, ep_rank = p.ep_square or (0, 0)
            lines.append(
                f"by def $en_passant_move({source}, {target}, {captured}, {side}, "
                f"{m.from_file}, {m.from_rank}, {m.to_file}, {m.to_rank}, "
                f"{ep_file}, {ep_rank}, {m.promotion})"
            )
        elif shape == "knight_move":
            lines.append(f"by def $knight_move({common}, {m.promotion})")
        elif shape == "bishop_move":
            lines.append(
                f"by def $bishop_move({common}, {len(blockers)}, {m.promotion})"
            )
        elif shape == "rook_move":
            lines.append(f"by def $rook_move({common}, {len(blockers)}, {m.promotion})")
        elif shape == "queen_move":
            lines.append(f"by def $queen_move({common}, {len(blockers)}, {m.promotion})")
        elif shape == "king_step":
            lines.append(f"by def $king_step({common}, {m.promotion})")
        else:
            rights = cls._rights(p)
            start_safe, transit_safe, end_safe = castle_safety
            if shape == "white_kingside_castle":
                lines.append(
                    f"by def $white_kingside_castle({source}, {p.piece_at(6,1)}, "
                    f"{p.piece_at(7,1)}, {p.piece_at(8,1)}, {rights['K']}, "
                    f"{m.from_file}, {m.from_rank}, {m.to_file}, {m.to_rank}, "
                    f"{m.promotion}, {start_safe}, {transit_safe}, {end_safe})"
                )
            elif shape == "white_queenside_castle":
                lines.append(
                    f"by def $white_queenside_castle({source}, {p.piece_at(2,1)}, "
                    f"{p.piece_at(3,1)}, {p.piece_at(4,1)}, {p.piece_at(1,1)}, "
                    f"{rights['Q']}, {m.from_file}, {m.from_rank}, {m.to_file}, "
                    f"{m.to_rank}, {m.promotion}, {start_safe}, {transit_safe}, {end_safe})"
                )
            elif shape == "black_kingside_castle":
                lines.append(
                    f"by def $black_kingside_castle({source}, {p.piece_at(6,8)}, "
                    f"{p.piece_at(7,8)}, {p.piece_at(8,8)}, {rights['k']}, "
                    f"{m.from_file}, {m.from_rank}, {m.to_file}, {m.to_rank}, "
                    f"{m.promotion}, {start_safe}, {transit_safe}, {end_safe})"
                )
            else:
                lines.append(
                    f"by def $black_queenside_castle({source}, {p.piece_at(2,8)}, "
                    f"{p.piece_at(3,8)}, {p.piece_at(4,8)}, {p.piece_at(1,8)}, "
                    f"{rights['q']}, {m.from_file}, {m.from_rank}, {m.to_file}, "
                    f"{m.to_rank}, {m.promotion}, {start_safe}, {transit_safe}, {end_safe})"
                )
        return lines

    @classmethod
    def _expected_board(
        cls, position: Position, move: Move, shape: str
    ) -> tuple[int, ...]:
        board = list(position.board)
        source = position.piece_at(move.from_file, move.from_rank)
        side = position.turn
        board[board_index(move.from_file, move.from_rank)] = 0

        if shape == "en_passant_move":
            board[board_index(move.to_file, move.from_rank)] = 0

        placed = side * move.promotion if shape == "pawn_promotion" else source
        board[board_index(move.to_file, move.to_rank)] = placed

        if shape.endswith("castle"):
            rank = move.from_rank
            rook_from, rook_to = ((8, 6) if move.to_file > move.from_file else (1, 4))
            board[board_index(rook_from, rank)] = 0
            board[board_index(rook_to, rank)] = side * ROOK
        return tuple(board)

    @staticmethod
    def _updated_castling(position: Position, move: Move) -> str:
        source = position.piece_at(move.from_file, move.from_rank)
        target = position.piece_at(move.to_file, move.to_rank)
        disabled: set[str] = set()
        if source == KING:
            disabled.update(("K", "Q"))
        elif source == -KING:
            disabled.update(("k", "q"))

        rook_flags = {
            (8, 1, ROOK): "K",
            (1, 1, ROOK): "Q",
            (8, 8, -ROOK): "k",
            (1, 8, -ROOK): "q",
        }
        source_flag = rook_flags.get((move.from_file, move.from_rank, source))
        target_flag = rook_flags.get((move.to_file, move.to_rank, target))
        if source_flag:
            disabled.add(source_flag)
        if target_flag:
            disabled.add(target_flag)
        return "".join(ch for ch in position.castling if ch not in disabled)

    @classmethod
    def _expected_metadata(
        cls, position: Position, move: Move, shape: str
    ) -> tuple[int, str, tuple[int, int] | None, int, int]:
        source = position.piece_at(move.from_file, move.from_rank)
        target = position.piece_at(move.to_file, move.to_rank)
        side = position.turn

        ep_square: tuple[int, int] | None = None
        if shape == "pawn_double_move":
            middle_rank = move.from_rank + side
            middle = (
                position.piece_at(move.from_file, middle_rank)
                if 1 <= middle_rank <= 8
                else 99
            )
            valid_double = (
                source == side
                and target == 0
                and middle == 0
                and move.promotion == 0
                and move.to_file == move.from_file
                and (
                    (side == 1 and move.from_rank == 2 and move.to_rank == 4)
                    or (side == -1 and move.from_rank == 7 and move.to_rank == 5)
                )
            )
            if valid_double:
                ep_square = (move.from_file, middle_rank)

        captured = target
        if shape == "en_passant_move":
            captured = position.piece_at(move.to_file, move.from_rank)
        halfmove = 0 if abs(source) == PAWN or captured != 0 else position.halfmove + 1
        fullmove = position.fullmove + int(position.turn == -1)
        return (
            -position.turn,
            cls._updated_castling(position, move),
            ep_square,
            halfmove,
            fullmove,
        )

    @classmethod
    def _agent_record(
        cls, transition: CandidateTransition
    ) -> tuple[list[str], str, int, int]:
        """Build the checked Agent-facing cover for the same transaction.

        The cover stays close to ordinary play—``move(e2,e4)`` and
        ``result(checkmate)``—while the detailed certificate that follows still
        checks geometry, occupancy, sparse board edits, metadata and king
        safety.  Failure anywhere rejects the whole transaction.
        """
        move = transition.move
        try:
            analysis = analyze_fen(transition.after.fen)
            outcome = str(analysis["status"])
            legal_count = int(analysis["legal_count"])
            checker_count, _ = cls._unsafe_count(
                transition.after, transition.after.turn
            )
            if outcome not in {"ongoing", "check", "checkmate", "stalemate"}:
                raise ValueError(f"unsupported status {outcome!r}")
        except Exception:
            outcome = "unclassified"
            checker_count = -1
            legal_count = -1

        record = make_agent_record(
            move.from_square,
            move.to_square,
            promotion=move.promotion,
            outcome=outcome,
            checker_count=checker_count,
            legal_reply_count=legal_count,
            uci=move.uci,
        )
        return record.litex().splitlines(), outcome, checker_count, legal_count

    def _board_certificate(
        self,
        before: Position,
        actual: Position,
        expected_board: tuple[int, ...],
    ) -> list[str]:
        """Emit the sole production board contract: a canonical sparse delta."""
        sparse_lines, _ = sparse_litex_lines(
            before.board, expected_board, actual.board
        )
        return [
            "# Board certificate: immutable board plus canonical sparse delta",
            *sparse_lines,
        ]

    @classmethod
    def _metadata_certificate(
        cls, transition: CandidateTransition, shape: str
    ) -> tuple[list[str], int]:
        q = transition.after
        expected_turn, expected_castling, expected_ep, expected_halfmove, expected_fullmove = (
            cls._expected_metadata(transition.before, transition.move, shape)
        )
        actual_rights = cls._rights(q)
        expected_rights = {key: int(key in expected_castling) for key in "KQkq"}
        actual_ep_file, actual_ep_rank = q.ep_square or (0, 0)
        expected_ep_file, expected_ep_rank = expected_ep or (0, 0)

        actual = (
            q.turn,
            actual_rights["K"], actual_rights["Q"],
            actual_rights["k"], actual_rights["q"],
            actual_ep_file, actual_ep_rank,
            q.halfmove, q.fullmove,
        )
        expected = (
            expected_turn,
            expected_rights["K"], expected_rights["Q"],
            expected_rights["k"], expected_rights["q"],
            expected_ep_file, expected_ep_rank,
            expected_halfmove, expected_fullmove,
        )
        mismatch_count = sum(a != b for a, b in zip(actual, expected))
        fact = (
            "by def $metadata_transition("
            f"{q.turn}, {expected_turn}, "
            f"{actual_rights['K']}, {expected_rights['K']}, "
            f"{actual_rights['Q']}, {expected_rights['Q']}, "
            f"{actual_rights['k']}, {expected_rights['k']}, "
            f"{actual_rights['q']}, {expected_rights['q']}, "
            f"{actual_ep_file}, {expected_ep_file}, "
            f"{actual_ep_rank}, {expected_ep_rank}, "
            f"{q.halfmove}, {expected_halfmove}, "
            f"{q.fullmove}, {expected_fullmove})"
        )
        return ["# State metadata certificate", fact], int(mismatch_count)

    def build_move_query(self, transition: CandidateTransition) -> BuiltQuery:
        p, q, m = transition.before, transition.after, transition.move
        shape = self._select_shape(transition)
        source = p.piece_at(m.from_file, m.from_rank)
        target = p.piece_at(m.to_file, m.to_rank)

        pre_opponent_unsafe, pre_opponent_king = self._unsafe_count(p, -p.turn)
        post_mover_unsafe, post_mover_king = self._unsafe_count(q, p.turn)
        castle_start_unsafe = 0
        castle_transit_unsafe = 0
        middle_comment = ""
        if shape.endswith("castle"):
            castle_start_unsafe, _ = self._unsafe_count(p, p.turn)
            middle = self._king_step_position(p, m)
            castle_transit_unsafe, transit_king = self._unsafe_count(middle, p.turn)
            middle_comment = (
                self._board_comment("CASTLE_TRANSIT", middle)
                + f"\n# Transit king square: {transit_king[0]},{transit_king[1]}"
            )

        expected_board = self._expected_board(p, m, shape)
        board_lines = self._board_certificate(p, q, expected_board)
        agent_lines, outcome, checker_count, legal_reply_count = self._agent_record(transition)
        metadata_lines, metadata_mismatches = self._metadata_certificate(transition, shape)
        unsafe_total = (
            pre_opponent_unsafe
            + post_mover_unsafe
            + castle_start_unsafe
            + castle_transit_unsafe
        )

        chunks: list[str] = [
            "\n".join(agent_lines),
            f"# Certificate SHA seed: {p.fen}|{m.uci}",
            "# board_transition_mode=sparse",
            self._board_comment("PRE", p),
            self._board_comment("POST", q),
            "# Coordinate, carrier, side, and moving-piece checks",
            f"by def $coordinate({m.from_file}, {m.from_rank})",
            f"by def $coordinate({m.to_file}, {m.to_rank})",
            f"by def $piece_code({source})",
            f"by def $piece_code({target})",
            f"by def $side_code({p.turn})",
            f"by def $moving_piece({source}, {p.turn})",
            (
                "by def $admissible_position("
                f"{self._king_count(p, 1)}, {self._king_count(p, -1)}, "
                f"{self._last_rank_pawn_count(p)}, {p.turn})"
            ),
            (
                f"# Pre-state non-moving king at {pre_opponent_king[0]},"
                f"{pre_opponent_king[1]}"
            ),
            f"by def $king_safe({self._king_count(p, -p.turn)}, {pre_opponent_unsafe})",
        ]
        if middle_comment:
            chunks.append(middle_comment)
            chunks.append(
                f"by def $king_safe({self._king_count(p, p.turn)}, {castle_start_unsafe})"
            )
            chunks.append(
                f"by def $king_safe({self._king_count(self._king_step_position(p, m), p.turn)}, "
                f"{castle_transit_unsafe})"
            )

        chunks.extend(
            self._shape_certificate(
                transition,
                shape,
                (
                    int(castle_start_unsafe == 0),
                    int(castle_transit_unsafe == 0),
                    int(post_mover_unsafe == 0),
                ),
            )
        )
        chunks.extend(
            [
                f"# Post-state moving king at {post_mover_king[0]},{post_mover_king[1]}",
                f"by def $king_safe({self._king_count(q, p.turn)}, {post_mover_unsafe})",
            ]
        )
        chunks.extend(board_lines)
        chunks.extend(metadata_lines)
        chunks.extend(
            [
                (
                    "by def $admissible_position("
                    f"{self._king_count(q, 1)}, {self._king_count(q, -1)}, "
                    f"{self._last_rank_pawn_count(q)}, {q.turn})"
                ),
                (
                    "by def $legal_transition("
                    f"1, {metadata_mismatches}, {unsafe_total}, "
                    f"{self._king_count(p, 1)}, {self._king_count(p, -1)}, "
                    f"{self._king_count(q, 1)}, {self._king_count(q, -1)}, "
                    f"{self._last_rank_pawn_count(p)}, {self._last_rank_pawn_count(q)})"
                ),
            ]
        )

        source_text = "\n\n".join(chunks).rstrip() + "\n"
        agent_source = "\n".join(agent_lines).rstrip() + "\n"
        return BuiltQuery(
            source=source_text,
            sha256=self._digest(source_text),
            kind="move-certificate",
            agent_source=agent_source,
            board_transition_mode=self.board_transition_mode,
            outcome=outcome,
            checker_count=checker_count,
            legal_reply_count=legal_reply_count,
        )

    def build_position_query(self, position: Position) -> BuiltQuery:
        unsafe, king_square = self._unsafe_count(position, -position.turn)
        chunks = [
            self._board_comment("ROOT", position),
            "# Root-position structural certificate",
            (
                "by def $admissible_position("
                f"{self._king_count(position, 1)}, {self._king_count(position, -1)}, "
                f"{self._last_rank_pawn_count(position)}, {position.turn})"
            ),
            f"# Non-moving king square: {king_square[0]},{king_square[1]}",
            f"by def $king_safe({self._king_count(position, -position.turn)}, {unsafe})",
        ]
        source_text = "\n\n".join(chunks).rstrip() + "\n"
        return BuiltQuery(
            source=source_text,
            sha256=self._digest(source_text),
            kind="position-certificate",
            board_transition_mode=self.board_transition_mode,
        )

    def as_standalone(self, query: BuiltQuery) -> str:
        return self.formal_source + "\n" + query.source
