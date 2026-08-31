from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import os

from .litex_gate import Gate
from .model import (
    BISHOP,
    KING,
    KNIGHT,
    PAWN,
    Move,
    Position,
    coords_to_square,
)
from .query import LitexQueryBuilder
from .transition_trace import piece_label
from .candidate import apply_candidate
from .fast_state import FastPosition, analyze_fen


@dataclass(slots=True)
class PositionStatusAnalyzer:
    gate: Gate
    query_builder: LitexQueryBuilder

    def attackers_to(self, position: Position, target_file: int, target_rank: int, attacker_side: int) -> list[dict[str, Any]]:
        attackers: list[dict[str, Any]] = []
        for source_file in range(1, 9):
            for source_rank in range(1, 9):
                piece = position.piece_at(source_file, source_rank)
                if piece == 0 or (1 if piece > 0 else -1) != attacker_side:
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
                        "path": [coords_to_square(*square) for square in path],
                    }
                )
        return attackers

    def king_checkers(self, position: Position, side: int | None = None) -> tuple[str, list[dict[str, Any]]]:
        king_side = position.turn if side is None else side
        king_file, king_rank = self.query_builder._find_king(position, king_side)
        return (
            coords_to_square(king_file, king_rank),
            self.attackers_to(position, king_file, king_rank, -king_side),
        )

    @staticmethod
    def known_dead_position(position: Position) -> dict[str, Any]:
        """Recognise a conservative subset of positions in which mate is impossible.

        The full FIDE dead-position definition quantifies over every legal move
        sequence.  This helper deliberately recognises only standard material
        cases whose answer is immediate, and labels the result accordingly.
        """

        non_kings: list[tuple[int, int, int]] = []
        bishops: list[tuple[int, int, int]] = []
        for file in range(1, 9):
            for rank in range(1, 9):
                piece = position.piece_at(file, rank)
                if piece == 0 or abs(piece) == KING:
                    continue
                non_kings.append((piece, file, rank))
                if abs(piece) == BISHOP:
                    bishops.append((piece, file, rank))
        if not non_kings:
            return {"known": True, "dead": True, "reason": "仅剩双王，任何合法序列都不可能将死。"}
        if len(non_kings) == 1 and abs(non_kings[0][0]) in {BISHOP, KNIGHT}:
            name = "单象" if abs(non_kings[0][0]) == BISHOP else "单马"
            return {"known": True, "dead": True, "reason": f"王加{name}对单王不能构成将死。"}
        if len(non_kings) == 2 and len(bishops) == 2:
            colors = {(file + rank) % 2 for _, file, rank in bishops}
            if len(colors) == 1:
                return {"known": True, "dead": True, "reason": "双方只剩同色格象，无法形成将死。"}
        return {
            "known": False,
            "dead": False,
            "reason": "保守识别器不作结论；完整死局判定需要考察是否存在任何可达将死序列。",
        }

    def analyze(
        self,
        position: Position,
        *,
        include_rejections: bool = False,
        audit_mode: str | None = None,
    ) -> dict[str, Any]:
        """Classify a position without submitting a 64x64 move grid to Litex.

        ``fast_state`` generates the exact finite pseudo-legal and king-safe
        move sets directly from the pieces that actually exist.  The normal
        workbench move gate remains the sole authority for *committing* a move.
        This status layer may optionally ask Litex to audit one witness or all
        host-generated legal moves; a terminal position needs no positive
        witness and therefore performs zero gate calls.
        """

        selected_audit = (
            audit_mode
            or os.environ.get("LITEX_STATUS_AUDIT", "witness")
        ).strip().lower()
        if selected_audit not in {"none", "witness", "all"}:
            raise ValueError("audit_mode must be none, witness, or all")

        king_square, checkers = self.king_checkers(position)
        fast = FastPosition.from_fen(position.fen)
        pseudo = list(fast.pseudo_legal())
        exact = analyze_fen(position.fen)
        legal_uci = [str(item) for item in exact["legal_uci"]]

        legal: list[dict[str, Any]] = []
        for uci in legal_uci:
            move = Move.from_uci(uci)
            transition = apply_candidate(position, move)
            legal.append(
                {
                    "uci": move.uci,
                    "from": move.from_square,
                    "to": move.to_square,
                    "promotion": move.to_dict()["promotion"],
                    "after_fen": transition.after.fen,
                }
            )

        legal_set = set(legal_uci)
        rejected: list[dict[str, Any]] = []
        if include_rejections:
            for candidate in pseudo:
                if candidate.uci in legal_set:
                    continue
                rejected.append(
                    {
                        "uci": candidate.uci,
                        "from": candidate.uci[:2],
                        "to": candidate.uci[2:4],
                        "reason": "精确几何候选在走后暴露本方王，未进入合法着集合。",
                    }
                )

        audit_targets = (
            []
            if selected_audit == "none" or not legal_uci
            else legal_uci
            if selected_audit == "all"
            else legal_uci[:1]
        )
        audit_rows: list[dict[str, Any]] = []
        for uci in audit_targets:
            _, receipt = self.gate.validate_move(position, Move.from_uci(uci))
            audit_rows.append(
                {
                    "uci": uci,
                    "accepted": bool(receipt.accepted),
                    "engine": receipt.engine,
                    "query_sha256": receipt.query_sha256,
                    "diagnostics": receipt.diagnostics[:2],
                }
            )

        status = str(exact["status"])
        dead = self.known_dead_position(position)
        return {
            "fen": position.fen,
            "turn": "white" if position.turn == 1 else "black",
            "king_square": king_square,
            "in_check": bool(exact["in_check"]),
            "checker_count": len(checkers),
            "checkers": checkers,
            "theoretical_pair_count": 4096,
            "candidate_count": len(pseudo),
            "pseudo_legal_count": len(pseudo),
            "legal_move_count": len(legal),
            "legal_count": len(legal),
            "legal_moves": legal,
            "rejected_count": len(pseudo) - len(legal),
            "rejected_moves": rejected,
            "status": status,
            "dead_position": dead,
            "halfmove": position.halfmove,
            "fifty_move_claim_available": position.halfmove >= 100,
            "seventy_five_move_automatic": position.halfmove >= 150,
            "audit": {
                "mode": selected_audit,
                "litex_call_count": len(audit_rows),
                "passed": all(row["accepted"] for row in audit_rows),
                "moves": audit_rows,
                "terminal_zero_call": not legal_uci,
            },
            "method": (
                "从当前实际棋子按类型生成精确伪合法着，再做走后王安全筛选；"
                "不枚举 64×64 源格—目标格。工作台实际落子仍必须经过完整 Litex 门禁。"
                f"本次状态展示的 Litex 审计模式为 {selected_audit}，调用 {len(audit_rows)} 次。"
            ),
        }

    def has_legal_en_passant(self, position: Position) -> bool:
        """Whether the FEN ep target corresponds to an actually legal capture.

        Repetition identity depends on *available* moves, not merely the raw FEN
        target.  The exact cached generator is sufficient here; no move is being
        committed, so repeatedly opening Litex blocks would only duplicate the
        history scan.
        """

        if position.ep_square is None:
            return False
        ep_name = coords_to_square(*position.ep_square)
        fast = analyze_fen(position.fen)
        for uci in fast["legal_uci"]:
            move = str(uci)
            if move[2:4] != ep_name:
                continue
            source = position.piece_at(ord(move[0]) - 96, int(move[1]))
            if abs(source) == PAWN and move[0] != move[2]:
                return True
        return False

    def repetition_key(self, position: Position) -> dict[str, Any]:
        placement, active, castling, ep, _, _ = position.fen.split()
        effective_ep = ep if ep != "-" and self.has_legal_en_passant(position) else "-"
        key = f"{placement} {active} {castling} {effective_ep}"
        return {
            "key": key,
            "placement": placement,
            "active": active,
            "castling": castling,
            "effective_ep": effective_ep,
            "ignored_halfmove": position.halfmove,
            "ignored_fullmove": position.fullmove,
        }

    def run_history(self, position: Position, sequence: list[str]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        timeline: list[dict[str, Any]] = []

        def append_entry(current: Position, *, ply: int, uci: str | None, accepted: bool, receipt: Any | None = None) -> None:
            key = self.repetition_key(current)
            counts[key["key"]] = counts.get(key["key"], 0) + 1
            occurrence = counts[key["key"]]
            timeline.append(
                {
                    "ply": ply,
                    "uci": uci,
                    "accepted": accepted,
                    "fen": current.fen,
                    "position": current.to_dict(),
                    "repetition_key": key,
                    "occurrence": occurrence,
                    "threefold_claim_available": occurrence >= 3,
                    "fivefold_automatic": occurrence >= 5,
                    "fifty_move_claim_available": current.halfmove >= 100,
                    "seventy_five_move_automatic": current.halfmove >= 150,
                    "receipt": None
                    if receipt is None
                    else {
                        "engine": receipt.engine,
                        "query_sha256": receipt.query_sha256,
                        "reason": receipt.reason,
                    },
                }
            )

        current = position
        append_entry(current, ply=0, uci=None, accepted=True)
        failure: dict[str, Any] | None = None
        for ply, uci in enumerate(sequence, start=1):
            move = Move.from_uci(uci)
            transition, receipt = self.gate.validate_move(current, move)
            if not receipt.accepted:
                failure = {
                    "ply": ply,
                    "uci": uci,
                    "reason": receipt.reason,
                    "diagnostics": receipt.diagnostics[:4],
                }
                break
            current = transition.after
            append_entry(current, ply=ply, uci=uci, accepted=True, receipt=receipt)

        final = timeline[-1]
        return {
            "accepted": failure is None,
            "failure": failure,
            "start_fen": position.fen,
            "sequence": sequence,
            "timeline": timeline,
            "final": final,
            "rules": {
                "threefold": "同一局面第三次出现时可以申和；不是自动终局。正式比赛也允许先登记一手不可更改的拟走之着，若该着将造成第三次出现即可提出申和。本实验只演示已提交节点。",
                "fivefold": "同一局面第五次出现时自动和棋。",
                "fifty_move": "双方各完成 50 手且期间无兵走、无吃子时可以申和；halfmove 达到 100。正式比赛也允许基于一手预先登记的拟走之着提出申和，本实验只演示已提交节点。",
                "seventy_five_move": "双方各完成 75 手且期间无兵走、无吃子时自动和棋；halfmove 达到 150，但最后一手将死优先。",
                "identity": "重复键只含棋子摆放、行棋方、易位权及真正可行的吃过路兵权；两个回合计数器不参与。",
            },
        }


def analyze_position(position: Position, *, audit_mode: str = "none") -> dict[str, Any]:
    """Lightweight module-level status API used by SAN, agents, and tests.

    This function does not commit a move and therefore performs no Litex call.
    It delegates exact candidate generation and king-safety filtering to
    ``fast_state``.  Actual workbench moves remain fail-closed behind the Litex
    gate.  ``audit_mode`` is accepted for API compatibility; callers that need
    witness/all auditing should use ``PositionStatusAnalyzer.analyze``.
    """
    if audit_mode not in {"none", "witness", "all"}:
        raise ValueError("audit_mode must be none, witness, or all")
    exact = analyze_fen(position.fen)
    status = str(exact["status"])
    return {
        "fen": position.fen,
        "status": status,
        "outcome": status,
        "in_check": bool(exact["in_check"]),
        "legal_count": int(exact["legal_count"]),
        "legal_reply_count": int(exact["legal_count"]),
        "legal_uci": list(exact["legal_uci"]),
        "pseudo_legal_count": int(exact["pseudo_legal_count"]),
        "audit": {
            "mode": "none",
            "litex_call_count": 0,
            "note": "status-only API; move commitment still requires the Litex gate",
        },
    }
