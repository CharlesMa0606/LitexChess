from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .model import (
    BISHOP,
    KING,
    KNIGHT,
    PAWN,
    QUEEN,
    ROOK,
    CandidateTransition,
    Position,
    coords_to_square,
)
from .query import LitexQueryBuilder
from .compact_transition import derive_delta

PIECE_NAMES_ZH = {
    0: "空格",
    PAWN: "白兵",
    KNIGHT: "白马",
    BISHOP: "白象",
    ROOK: "白车",
    QUEEN: "白后",
    KING: "白王",
    -PAWN: "黑兵",
    -KNIGHT: "黑马",
    -BISHOP: "黑象",
    -ROOK: "黑车",
    -QUEEN: "黑后",
    -KING: "黑王",
}

SHAPE_NAMES_ZH = {
    "pawn_single_move": "兵单步",
    "pawn_double_move": "兵双步",
    "pawn_capture": "兵普通吃子",
    "pawn_promotion": "兵升变",
    "en_passant_move": "吃过路兵",
    "knight_move": "马的普通走法",
    "bishop_move": "象的普通走法",
    "rook_move": "车的普通走法",
    "queen_move": "后的普通走法",
    "king_step": "王的一步",
    "white_kingside_castle": "白方王翼易位",
    "white_queenside_castle": "白方后翼易位",
    "black_kingside_castle": "黑方王翼易位",
    "black_queenside_castle": "黑方后翼易位",
}

SHAPE_EXPLANATIONS_ZH = {
    "pawn_single_move": "核对同纵线、前进一格、目标为空且未携带升变参数。",
    "pawn_double_move": "核对兵在初始横线、前进两格，并且中间格与目标格都为空。",
    "pawn_capture": "核对兵斜向前一格，目标格是敌方非王棋子。",
    "pawn_promotion": "核对兵到达最后一横线，并明确升变为马、象、车或后。",
    "en_passant_move": "核对目标格等于当前局面的过路兵目标，并移除相邻敌兵。",
    "knight_move": "核对坐标差为 (1,2) 或 (2,1)；马不需要路径清空。",
    "bishop_move": "核对对角线几何，并要求路径阻挡数为零。",
    "rook_move": "核对同横线或同纵线几何，并要求路径阻挡数为零。",
    "queen_move": "核对象或车的几何之一成立，并要求路径阻挡数为零。",
    "king_step": "核对王只走相邻一格；走后王安全由另一组证书负责。",
    "white_kingside_castle": "核对 e1、f1、g1、h1，白方 K 易位权以及起点、经过格、终点安全。",
    "white_queenside_castle": "核对 e1、d1、c1、b1、a1，白方 Q 易位权以及三段安全。",
    "black_kingside_castle": "核对 e8、f8、g8、h8，黑方 k 易位权以及三段安全。",
    "black_queenside_castle": "核对 e8、d8、c8、b8、a8，黑方 q 易位权以及三段安全。",
}

CALL_RE = re.compile(r"^by def \$([A-Za-z_][A-Za-z0-9_]*)\(")


def piece_label(code: int) -> str:
    return PIECE_NAMES_ZH.get(code, f"未知编码 {code}")


def fen_fields(position: Position) -> dict[str, Any]:
    placement, active, castling, ep, halfmove, fullmove = position.fen.split()
    return {
        "placement": placement,
        "active": active,
        "active_text": "白方走" if active == "w" else "黑方走",
        "castling": castling,
        "ep": ep,
        "halfmove": int(halfmove),
        "fullmove": int(fullmove),
    }


def _metadata_display(field: str, value: Any) -> str:
    if field == "turn":
        return "白方" if value == 1 else "黑方"
    if field == "castling":
        return value or "-"
    if field == "ep_square":
        return "-" if value is None else coords_to_square(*value)
    return str(value)


def _predicate_group(name: str, shape: str) -> str:
    if name == shape or name == "path_clear":
        return "shape"
    if name in {"coordinate", "piece_code", "side_code", "moving_piece", "admissible_position"}:
        return "precondition"
    if name == "king_safe":
        return "safety"
    if name in {"sparse_square_edit", "sparse_board_transition"}:
        return "board"
    if name in {"square", "move", "promotion_choice", "result", "result_witness"}:
        return "agent"
    if name == "metadata_transition":
        return "metadata"
    if name == "legal_transition":
        return "total"
    return "other"


class TransitionTraceBuilder:
    """Build a transparent, pedagogical trace for one concrete move certificate.

    This class does not authorize moves.  It exposes the work already performed
    by the mechanical candidate transformer and the deterministic certificate
    compiler, so the textbook can distinguish host-side computation from what
    Litex actually checks.
    """

    def __init__(self, query_builder: LitexQueryBuilder) -> None:
        self.query_builder = query_builder

    def _attackers(self, position: Position, king_side: int) -> tuple[list[dict[str, Any]], str]:
        king_file, king_rank = self.query_builder._find_king(position, king_side)
        attacker_side = -king_side
        attackers: list[dict[str, Any]] = []
        for source_file in range(1, 9):
            for source_rank in range(1, 9):
                piece = position.piece_at(source_file, source_rank)
                if self.query_builder._sign(piece) != attacker_side:
                    continue
                if not self.query_builder._piece_attacks(
                    position,
                    piece,
                    source_file,
                    source_rank,
                    king_file,
                    king_rank,
                ):
                    continue
                path = self.query_builder._squares_between(
                    source_file,
                    source_rank,
                    king_file,
                    king_rank,
                )
                blockers = [
                    square
                    for square in path
                    if position.piece_at(*square) != 0
                ]
                attackers.append(
                    {
                        "square": coords_to_square(source_file, source_rank),
                        "piece": piece,
                        "piece_name": piece_label(piece),
                        "king_square": coords_to_square(king_file, king_rank),
                        "path": [coords_to_square(*square) for square in path],
                        "blockers": [coords_to_square(*square) for square in blockers],
                    }
                )
        return attackers, coords_to_square(king_file, king_rank)

    def _attackers_to_square(
        self,
        position: Position,
        square: str,
        attacker_side: int,
    ) -> list[dict[str, Any]]:
        target_file = ord(square[0]) - 96
        target_rank = int(square[1])
        attackers: list[dict[str, Any]] = []
        for source_file in range(1, 9):
            for source_rank in range(1, 9):
                piece = position.piece_at(source_file, source_rank)
                if self.query_builder._sign(piece) != attacker_side:
                    continue
                if not self.query_builder._piece_attacks(
                    position,
                    piece,
                    source_file,
                    source_rank,
                    target_file,
                    target_rank,
                ):
                    continue
                path = self.query_builder._squares_between(
                    source_file,
                    source_rank,
                    target_file,
                    target_rank,
                )
                attackers.append(
                    {
                        "square": coords_to_square(source_file, source_rank),
                        "piece": piece,
                        "piece_name": piece_label(piece),
                        "target_square": square,
                        "path": [coords_to_square(*item) for item in path],
                    }
                )
        return attackers

    @staticmethod
    def _castling_right_reasons(transition: CandidateTransition, expected_castling: str) -> list[dict[str, str]]:
        before = transition.before
        move = transition.move
        source = before.piece_at(move.from_file, move.from_rank)
        target = before.piece_at(move.to_file, move.to_rank)
        removed = [flag for flag in before.castling if flag not in expected_castling]
        reasons: list[dict[str, str]] = []
        rook_origins = {
            "K": (8, 1, ROOK, "白方 h1 车移动或在 h1 被吃"),
            "Q": (1, 1, ROOK, "白方 a1 车移动或在 a1 被吃"),
            "k": (8, 8, -ROOK, "黑方 h8 车移动或在 h8 被吃"),
            "q": (1, 8, -ROOK, "黑方 a8 车移动或在 a8 被吃"),
        }
        for flag in removed:
            if flag in {"K", "Q"} and source == KING:
                reason = "白王已经移动；K、Q 权利同时永久移除"
            elif flag in {"k", "q"} and source == -KING:
                reason = "黑王已经移动；k、q 权利同时永久移除"
            else:
                file, rank, rook_code, fallback = rook_origins[flag]
                if (move.from_file, move.from_rank, source) == (file, rank, rook_code):
                    reason = fallback
                elif (move.to_file, move.to_rank, target) == (file, rank, rook_code):
                    reason = fallback
                else:
                    reason = "由历史状态更新规则移除"
            reasons.append({"right": flag, "reason": reason})
        return reasons

    @staticmethod
    def _candidate_operations(transition: CandidateTransition) -> list[dict[str, Any]]:
        p, q, move = transition.before, transition.after, transition.move
        operations: list[dict[str, Any]] = [
            {
                "kind": "clear-source",
                "title": "清空源格",
                "square": move.from_square,
                "before": transition.source_piece,
                "before_name": piece_label(transition.source_piece),
                "after": 0,
                "after_name": piece_label(0),
            }
        ]
        if transition.is_en_passant and transition.captured_square is not None:
            operations.append(
                {
                    "kind": "remove-en-passant-pawn",
                    "title": "移除被吃的过路兵",
                    "square": coords_to_square(*transition.captured_square),
                    "before": transition.captured_piece,
                    "before_name": piece_label(transition.captured_piece),
                    "after": 0,
                    "after_name": piece_label(0),
                }
            )
        elif transition.target_piece != 0:
            operations.append(
                {
                    "kind": "capture-target",
                    "title": "覆盖目标格上的被吃棋子",
                    "square": move.to_square,
                    "before": transition.target_piece,
                    "before_name": piece_label(transition.target_piece),
                    "after": q.piece_at(move.to_file, move.to_rank),
                    "after_name": piece_label(q.piece_at(move.to_file, move.to_rank)),
                }
            )
        operations.append(
            {
                "kind": "place-target",
                "title": "在目标格放置移动后的棋子",
                "square": move.to_square,
                "before": transition.target_piece,
                "before_name": piece_label(transition.target_piece),
                "after": q.piece_at(move.to_file, move.to_rank),
                "after_name": piece_label(q.piece_at(move.to_file, move.to_rank)),
            }
        )
        if transition.is_castle:
            rank = move.from_rank
            rook_from, rook_to = ((8, 6) if move.to_file > move.from_file else (1, 4))
            operations.append(
                {
                    "kind": "castle-rook",
                    "title": "同步移动易位车",
                    "from": coords_to_square(rook_from, rank),
                    "to": coords_to_square(rook_to, rank),
                    "piece": p.turn * ROOK,
                    "piece_name": piece_label(p.turn * ROOK),
                }
            )
        if transition.is_promotion:
            operations.append(
                {
                    "kind": "promotion",
                    "title": "把兵替换为升变棋子",
                    "square": move.to_square,
                    "promotion_code": move.promotion,
                    "piece_name": piece_label(p.turn * move.promotion) if move.promotion else "未提供升变棋子",
                }
            )
        return operations

    def build(
        self,
        transition: CandidateTransition,
        *,
        teaching_targets: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        p, q, move = transition.before, transition.after, transition.move
        shape = self.query_builder._select_shape(transition)
        path_squares = self.query_builder._squares_between(
            move.from_file,
            move.from_rank,
            move.to_file,
            move.to_rank,
        )
        blockers = self.query_builder._path_blockers(
            p,
            move.from_file,
            move.from_rank,
            move.to_file,
            move.to_rank,
        )
        expected_board = self.query_builder._expected_board(p, move, shape)
        (
            expected_turn,
            expected_castling,
            expected_ep,
            expected_halfmove,
            expected_fullmove,
        ) = self.query_builder._expected_metadata(p, move, shape)
        expected_position = Position(
            expected_board,
            turn=expected_turn,
            castling=expected_castling,
            ep_square=expected_ep,
            halfmove=expected_halfmove,
            fullmove=expected_fullmove,
        )

        delta = derive_delta(p.board, expected_board, q.board)
        board_mismatch_count = sum(
            actual != expected
            for actual, expected in zip(q.board, expected_board)
        )
        changed_squares: list[dict[str, Any]] = [
            {
                "square": edit.algebraic,
                "index": edit.index,
                "before": edit.before,
                "actual": q.board[edit.index],
                "expected": edit.after,
                "match": q.board[edit.index] == edit.after,
                "changed": True,
                "before_name": piece_label(edit.before),
                "actual_name": piece_label(q.board[edit.index]),
                "expected_name": piece_label(edit.after),
                "weight": edit.weight,
                "contribution": edit.contribution,
                "litex_call": (
                    "by def $sparse_square_edit("
                    f"{edit.index}, {edit.before}, {edit.after}, "
                    f"{edit.weight}, {edit.contribution})"
                ),
            }
            for edit in delta.edits
        ]

        # The production trace contains only the local sparse edits and the
        # exact collision-free board-code equation.

        metadata_values = [
            ("turn", "下一手行棋方", p.turn, q.turn, expected_turn),
            ("castling", "易位权", p.castling, q.castling, expected_castling),
            ("ep_square", "过路兵目标格", p.ep_square, q.ep_square, expected_ep),
            ("halfmove", "半回合计数", p.halfmove, q.halfmove, expected_halfmove),
            ("fullmove", "完整回合数", p.fullmove, q.fullmove, expected_fullmove),
        ]
        metadata_rows: list[dict[str, Any]] = []
        metadata_mismatch_count = 0
        for field, label, before, actual, expected in metadata_values:
            match = actual == expected
            metadata_mismatch_count += int(not match)
            metadata_rows.append(
                {
                    "field": field,
                    "label": label,
                    "before": _metadata_display(field, before),
                    "candidate": _metadata_display(field, actual),
                    "expected": _metadata_display(field, expected),
                    "match": match,
                }
            )

        pre_attackers, pre_king = self._attackers(p, -p.turn)
        post_attackers, post_king = self._attackers(q, p.turn)
        safety_stages: list[dict[str, Any]] = [
            {
                "id": "pre-non-moving-king",
                "label": "走子前：非行棋方的王",
                "position": "before",
                "king_square": pre_king,
                "attacker_count": len(pre_attackers),
                "attackers": pre_attackers,
                "required_safe": True,
                "why": "排除根局面中‘刚走完的一方自己的王仍在受将’这类非法状态。",
            }
        ]
        if shape.endswith("castle"):
            start_attackers, start_king = self._attackers(p, p.turn)
            transit_position = self.query_builder._king_step_position(p, move)
            transit_attackers, transit_king = self._attackers(transit_position, p.turn)
            safety_stages.extend(
                [
                    {
                        "id": "castle-start",
                        "label": "易位起点安全",
                        "position": "before",
                        "king_square": start_king,
                        "attacker_count": len(start_attackers),
                        "attackers": start_attackers,
                        "required_safe": True,
                        "why": "王不能在受将时开始易位。",
                    },
                    {
                        "id": "castle-transit",
                        "label": "易位经过格安全",
                        "position": "transit",
                        "fen": transit_position.fen,
                        "king_square": transit_king,
                        "attacker_count": len(transit_attackers),
                        "attackers": transit_attackers,
                        "required_safe": True,
                        "why": "王不能穿越受攻击格。",
                    },
                ]
            )
        safety_stages.append(
            {
                "id": "post-moving-king",
                "label": "走子后：行棋方的王",
                "position": "candidate-after",
                "king_square": post_king,
                "attacker_count": len(post_attackers),
                "attackers": post_attackers,
                "required_safe": True,
                "why": "任何走法都不能让本方王在走后仍受攻击。",
            }
        )
        unsafe_total = sum(stage["attacker_count"] for stage in safety_stages)

        # Tactical effects are explanatory rather than additional acceptance
        # conditions.  They expose whether the accepted candidate gives check,
        # opens a line (discovered check), or produces two simultaneous checks.
        opponent_before_attackers, opponent_before_king = self._attackers(p, -p.turn)
        opponent_after_attackers, opponent_after_king = self._attackers(q, -p.turn)
        checker_squares = {item["square"] for item in opponent_after_attackers}
        moved_piece_is_checker = move.to_square in checker_squares
        checker_count = len(opponent_after_attackers)
        if checker_count >= 2:
            check_kind = "double-check"
            check_label = "双将"
        elif checker_count == 1 and not moved_piece_is_checker:
            check_kind = "discovered-check"
            check_label = "闪将"
        elif checker_count == 1:
            check_kind = "check"
            check_label = "将军"
        else:
            check_kind = "none"
            check_label = "未将军"

        target_effects: list[dict[str, Any]] = []
        for target in teaching_targets or []:
            square = str(target.get("square", "")).lower()
            attacker_side = int(target.get("attacker_side", p.turn))
            before_target_attackers = self._attackers_to_square(p, square, attacker_side)
            after_target_attackers = self._attackers_to_square(q, square, attacker_side)
            target_effects.append(
                {
                    "square": square,
                    "label": target.get("label", square),
                    "attacker_side": attacker_side,
                    "before_attackers": before_target_attackers,
                    "after_attackers": after_target_attackers,
                    "opened": not before_target_attackers and bool(after_target_attackers),
                    "closed": bool(before_target_attackers) and not after_target_attackers,
                }
            )

        built_query = self.query_builder.build_move_query(transition)
        calls: list[dict[str, str]] = []
        for raw in built_query.source.splitlines():
            line = raw.strip()
            match = CALL_RE.match(line)
            if not match:
                continue
            predicate = match.group(1)
            calls.append(
                {
                    "predicate": predicate,
                    "group": _predicate_group(predicate, shape),
                    "source": line,
                }
            )
        group_counts = dict(Counter(call["group"] for call in calls))

        castling_removed = self._castling_right_reasons(transition, expected_castling)
        ep_reason = (
            f"兵双步经过 {coords_to_square(*expected_ep)}，因此只为下一手设置该过路兵目标。"
            if expected_ep is not None
            else "本手不是被证实的兵双步，因此过路兵目标清空。"
        )
        halfmove_reason = (
            "兵走或发生吃子，五十回合规则的半回合计数归零。"
            if abs(transition.source_piece) == PAWN or transition.captured_piece != 0
            else "既不是兵走也没有吃子，半回合计数加一。"
        )
        fullmove_reason = (
            "黑方走完后完整回合数加一。"
            if p.turn == -1
            else "白方走完后仍处于同一完整回合编号。"
        )

        return {
            "move": move.to_dict(),
            "shape": {
                "id": shape,
                "name": SHAPE_NAMES_ZH.get(shape, shape),
                "explanation": SHAPE_EXPLANATIONS_ZH.get(shape, "核对所选走子形状的具体参数。"),
            },
            "before": p.to_dict(),
            "candidate_after": q.to_dict(),
            "expected_after": expected_position.to_dict(),
            "fen": {
                "before": fen_fields(p),
                "candidate_after": fen_fields(q),
                "expected_after": fen_fields(expected_position),
                "explanation": "FEN 不是另一个合法性引擎，而是 Position 的六字段序列化；其中易位权与过路兵格保存了仅靠棋子摆放无法恢复的历史信息。",
            },
            "candidate_operations": self._candidate_operations(transition),
            "path": {
                "squares": [coords_to_square(*square) for square in path_squares],
                "blockers": [
                    {
                        "square": coords_to_square(*square),
                        "piece": p.piece_at(*square),
                        "piece_name": piece_label(p.piece_at(*square)),
                    }
                    for square in blockers
                ],
                "blocker_count": len(blockers),
            },
            "board_certificate": {
                "mode": self.query_builder.board_transition_mode,
                "encoding": "injective-base16",
                "edit_count": len(delta.edits),
                "edits": changed_squares,
                "mismatch_count": int(board_mismatch_count),
                "duplicate_count": delta.duplicate_count,
                "before_mismatch_count": delta.before_mismatch_count,
                "after_mismatch_count": delta.after_mismatch_count,
                "before_code": delta.before_code,
                "expected_after_code": delta.expected_after_code,
                "actual_after_code": delta.actual_after_code,
                "before_code_hex": hex(delta.before_code),
                "expected_after_code_hex": hex(delta.expected_after_code),
                "actual_after_code_hex": hex(delta.actual_after_code),
                "delta_code": delta.delta_code,
                "exact": delta.exact,
                "rank_check_count": 0,
                "rank_checks": [],
                "legacy_cell_comparisons": 0,
                "changed_squares": changed_squares,
                "explanation": (
                    "生产模式把棋盘视为不可变对象，只列出本手实际改变的 2--4 格；"
                    "每个局部编辑给出精确的 16 进制位权贡献，sparse_board_transition "
                    "再证明这些贡献把走前全盘码唯一地变成走后全盘码。该编码无碰撞，"
                    "因此无需在每一手重复比较 64 格；旧横线比较已移出生产规则内核。"
                ),
            },
            "metadata_certificate": {
                "mismatch_count": metadata_mismatch_count,
                "rows": metadata_rows,
                "castling_removed": castling_removed,
                "ep_reason": ep_reason,
                "halfmove_reason": halfmove_reason,
                "fullmove_reason": fullmove_reason,
                "explanation": "metadata_transition 逐项比较候选局面的轮次、四项易位权、过路兵格和两个计数器。",
            },
            "safety_certificate": {
                "stages": safety_stages,
                "unsafe_total": unsafe_total,
                "explanation": (
                    "当前版本的攻击扫描与攻击者计数由 Python 证书编译器计算，Litex 检查 king_safe 中的唯一王计数与零攻击者汇总。"
                    "这部分仍在可信计算基内，并非 Litex 自己从 64 格通用量化推导。"
                ),
            },
            "tactical_effects": {
                "opponent_king_square_before": opponent_before_king,
                "opponent_king_square_after": opponent_after_king,
                "before_checker_count": len(opponent_before_attackers),
                "before_checkers": opponent_before_attackers,
                "after_checker_count": checker_count,
                "after_checkers": opponent_after_attackers,
                "moved_piece_is_checker": moved_piece_is_checker,
                "kind": check_kind,
                "label": check_label,
                "target_effects": target_effects,
                "explanation": (
                    "这里是在候选后继上重新扫描对方王与指定教学目标。它用于解释闪将、双将与相对牵制，"
                    "不新增一条独立的合法性规则；攻击扫描仍由 Python 证书编译器完成。"
                ),
            },
            "certificate": {
                "sha256": built_query.sha256,
                "calls": calls,
                "group_counts": group_counts,
                "source": built_query.source,
            },
            "pipeline": [
                {
                    "index": 1,
                    "owner": "浏览器 / API",
                    "title": "提交候选走法",
                    "detail": f"只提交 {move.uci} 与父局面；前端没有接受权限。",
                },
                {
                    "index": 2,
                    "owner": "Python · candidate.py",
                    "title": "机械构造候选后继",
                    "detail": "移动棋子，并同步构造易位车、吃过路兵、升变、轮次、易位权、过路兵格与计数器；此阶段不返回合法/非法。",
                },
                {
                    "index": 3,
                    "owner": "Python · query.py",
                    "title": "独立重算期望后继与证书参数",
                    "detail": "重新选择走子形状、计算路径阻挡、2--4 格规范稀疏变更、精确全盘码、FEN 元数据与王安全计数。",
                },
                {
                    "index": 4,
                    "owner": "Litex",
                    "title": "展开固定谓词并核对具体事实",
                    "detail": "检查 Agent 走法记录、形状谓词、稀疏棋盘变更、metadata_transition、king_safe 与总合同。",
                },
                {
                    "index": 5,
                    "owner": "后端应用层",
                    "title": "接受才提交，拒绝则保持原局面",
                    "detail": "只有 Litex 回执全部成功才把 after 写入棋谱树；错误、超时或任一失败都按 fail-closed 拒绝。",
                },
            ],
            "trust_boundary": {
                "litex_checks": [
                    "具体坐标和棋子编码约束",
                    "选定走子形状的等式与不等式",
                    "2--4 个局部格编辑及精确全盘码增量等式",
                    "候选与期望 FEN 元数据相等",
                    "给定王计数与攻击者计数满足安全汇总",
                    "最终 mismatch 与 unsafe 计数为零",
                ],
                "python_computes": [
                    "机械候选后继",
                    "走子形状选择",
                    "滑行路径与阻挡数",
                    "独立期望后继与规范稀疏变更",
                    "易位权、过路兵格和计数器的期望值",
                    "攻击扫描与不安全攻击者计数",
                ],
            },
        }
