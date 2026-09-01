"""Interactive basic-endgame lessons backed by the ordinary Litex move gate.

The catalogue describes teaching goals.  ``EndgameTrainer`` owns short-lived
in-memory lesson sessions.  Every learner move and every automatic defender
move is submitted through exactly the same ``Gate.validate_move`` path as the
main workbench.  The fast move generator is used only to enumerate choices and
rank a deterministic defensive reply; it never commits a move by itself.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlencode

from .fast_state import FastPosition, Move as FastMove, analyze_fen
from .game_status import PositionStatusAnalyzer
from .litex_gate import Gate
from .model import Move, Position
from .presentation import render_san


@dataclass(frozen=True, slots=True)
class EndgameLesson:
    lesson_id: str
    title: str
    fen: str
    learner_side: str
    goal: str
    explanation: str
    principles: tuple[str, ...]
    max_plies: int = 80

    def json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["workbench_url"] = "/textbook/Chess/workbench?" + urlencode({"fen": self.fen, "lesson": self.lesson_id, "return": "/textbook/Chess/interactive-endgames"})
        return payload


LESSONS: dict[str, EndgameLesson] = {
    "rook-mate-box": EndgameLesson(
        "rook-mate-box",
        "单车杀王：先建立盒子",
        "8/8/8/8/3k4/8/6K1/7R w - - 0 1",
        "w",
        "checkmate",
        "先用车限制敌王活动区，再让己王靠近；每一步都要避免车被吃和无意逼和。",
        ("车与敌王保持安全距离", "逐步缩小盒子", "己王必须参与", "最后一将由己王封锁逃格"),
    ),
    "rook-mate-edge": EndgameLesson(
        "rook-mate-edge",
        "单车杀王：边线收官",
        "8/8/8/8/8/4K3/6R1/7k w - - 0 1",
        "w",
        "checkmate",
        "敌王已到边线。让己王控制相邻逃格，再用车沿边线完成最后一将。",
        ("先确认车不会被王吃", "己王控制逃格", "最后用车将军", "无将军且零合法着是逼和"),
        max_plies=40,
    ),
    "queen-mate": EndgameLesson(
        "queen-mate",
        "单后杀王：限制与防逼和",
        "8/8/8/8/3k4/8/6K1/7Q w - - 0 1",
        "w",
        "checkmate",
        "后能快速缩小空间，但也最容易过度封锁。先限制、再靠王、最后将杀。",
        ("后先限制", "王再靠近", "每一步检查敌王是否仍有合法格", "最后一将必须受己王保护"),
    ),
    "knight-dead": EndgameLesson(
        "knight-dead",
        "单马对单王：为什么是死局",
        "8/8/8/8/3k4/8/6K1/7N w - - 0 1",
        "w",
        "dead-position",
        "王马对单王不可能在任何合法续着中形成将死，所以不是等待申和，而是死局自动和棋。",
        ("不能强杀不总等于死局", "单马对单王属于可直接确认的死局", "双马对单王则不是同一概念"),
        max_plies=0,
    ),
    "bishop-dead": EndgameLesson(
        "bishop-dead",
        "单象对单王：同样属于死局",
        "8/8/8/8/3k4/8/6K1/7B w - - 0 1",
        "w",
        "dead-position",
        "王象对单王同样不可能在任何合法续着中形成将死。这里强调规则意义的死局，而不是单纯的‘无法强制取胜’。",
        ("单象无法独立完成将死", "死局立即终止", "不要把死局与逼和混为一谈"),
        max_plies=0,
    ),
}


@dataclass(slots=True)
class TrainingSession:
    training_id: str
    lesson: EndgameLesson
    position: Position
    history: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)
    warning: str | None = None


class EndgameTrainer:
    """In-memory interactive trainer that delegates all move acceptance to Litex."""

    def __init__(self, gate: Gate) -> None:
        self.gate = gate
        self._sessions: dict[str, TrainingSession] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _fast_to_model(move: FastMove) -> Move:
        return Move.from_uci(move.uci)

    @staticmethod
    def _status(position: Position) -> dict[str, Any]:
        analysis = dict(analyze_fen(position.fen))
        analysis["dead_position"] = PositionStatusAnalyzer.known_dead_position(position)
        return analysis

    @staticmethod
    def _king_metrics(position: Position) -> tuple[int | None, int | None]:
        fast = FastPosition.from_fen(position.fen)
        wk, bk = fast.king_square("w"), fast.king_square("b")
        distance = None
        if wk >= 0 and bk >= 0:
            distance = max(abs(wk % 8 - bk % 8), abs(wk // 8 - bk // 8))
        defender = bk if position.turn == 1 else wk
        edge = None
        if defender >= 0:
            edge = min(defender % 8, 7 - defender % 8, defender // 8, 7 - defender // 8)
        return distance, edge

    @classmethod
    def _hint(cls, position: Position, analysis: dict[str, Any]) -> str:
        dead = analysis.get("dead_position", {})
        if dead.get("dead"):
            return "本局面是死局：任何合法续着都不可能形成将死。"
        status = analysis.get("status")
        if status == "checkmate":
            return "完成：对方正在被将军且没有任何合法应对。"
        if status == "stalemate":
            return "这是逼和：对方未被将军却没有合法着。回退并给敌王保留至少一个逃格。"
        distance, edge = cls._king_metrics(position)
        if edge is not None and edge > 0:
            return "先用车或后缩小敌王活动区域，把敌王逐步赶向边线。"
        if distance is not None and distance > 2:
            return "敌王已接近边线；现在让己王靠近，控制最后几个逃格。"
        if analysis.get("in_check"):
            return "当前是将军，但仍有应对；检查能否继续缩小逃格而不丢重子。"
        return "先确认重子安全，再寻找由己王保护的最后一将；同时避免无将军的零合法着。"

    @staticmethod
    def _piece_count(position: Position, side: int) -> int:
        return sum(1 for piece in position.board if piece * side > 0)

    @classmethod
    def _finished(cls, session: TrainingSession, analysis: dict[str, Any]) -> tuple[bool, str]:
        dead = analysis.get("dead_position", {})
        if dead.get("dead"):
            success = session.lesson.goal == "dead-position"
            return True, "success" if success else "dead-position"
        status = str(analysis.get("status"))
        if status == "checkmate":
            # The side to move is the mated side.  A white learner succeeds when black is to move.
            learner_won = session.position.turn == -1 if session.lesson.learner_side == "w" else session.position.turn == 1
            return True, "success" if learner_won else "failed"
        if status == "stalemate":
            return True, "stalemate"
        learner_side = 1 if session.lesson.learner_side == "w" else -1
        # Losing the training rook/queen ends the attempt.  Kings are always retained by the gate.
        if session.lesson.lesson_id.startswith("rook") and not any(piece == 4 * learner_side for piece in session.position.board):
            return True, "heavy-piece-lost"
        if session.lesson.lesson_id.startswith("queen") and not any(piece == 5 * learner_side for piece in session.position.board):
            return True, "heavy-piece-lost"
        if len(session.history) >= session.lesson.max_plies > 0:
            return True, "move-limit"
        return False, "ongoing"

    @staticmethod
    def _legal_rows(position: Position) -> list[dict[str, Any]]:
        fast = FastPosition.from_fen(position.fen)
        rows: list[dict[str, Any]] = []
        for move in fast.legal_moves():
            rows.append(
                {
                    "uci": move.uci,
                    "from": move.uci[:2],
                    "to": move.uci[2:4],
                    "promotion": move.promotion or None,
                }
            )
        return rows

    def _public(self, session: TrainingSession, *, last_receipts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        analysis = self._status(session.position)
        finished, result = self._finished(session, analysis)
        learner_turn = (session.position.turn == 1) == (session.lesson.learner_side == "w")
        legal_moves = self._legal_rows(session.position) if learner_turn and not finished else []
        distance, edge = self._king_metrics(session.position)
        return {
            "training_id": session.training_id,
            "lesson": session.lesson.json(),
            "position": session.position.to_dict(),
            "fen": session.position.fen,
            "turn": "white" if session.position.turn == 1 else "black",
            "learner_turn": learner_turn,
            "legal_moves": legal_moves,
            "legal_sources": sorted({row["from"] for row in legal_moves}),
            "history": list(session.history),
            "analysis": analysis,
            "feedback": {
                "hint": self._hint(session.position, analysis),
                "king_distance": distance,
                "defender_edge_distance": edge,
                "warning": session.warning,
            },
            "finished": finished,
            "result": result,
            "last_receipts": last_receipts or [],
            "workbench_url": "/textbook/Chess/workbench?" + urlencode({"fen": session.position.fen, "lesson": session.lesson.lesson_id, "return": "/textbook/Chess/interactive-endgames"}),
        }

    def list_lessons(self) -> list[dict[str, Any]]:
        return [lesson.json() for lesson in LESSONS.values()]

    def lesson(self, lesson_id: str) -> dict[str, Any]:
        try:
            item = LESSONS[lesson_id]
        except KeyError as exc:
            raise KeyError(f"unknown endgame lesson: {lesson_id}") from exc
        position = Position.from_fen(item.fen)
        return {**item.json(), "analysis": self._status(position)}

    def start(self, lesson_id: str) -> dict[str, Any]:
        try:
            item = LESSONS[lesson_id]
        except KeyError as exc:
            raise KeyError(f"unknown endgame lesson: {lesson_id}") from exc
        session = TrainingSession(uuid.uuid4().hex[:16], item, Position.from_fen(item.fen))
        with self._lock:
            self._sessions[session.training_id] = session
        return self._public(session)

    def get(self, training_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                session = self._sessions[training_id]
            except KeyError as exc:
                raise KeyError(f"unknown endgame training session: {training_id}") from exc
        with session.lock:
            return self._public(session)

    def delete(self, training_id: str) -> None:
        with self._lock:
            self._sessions.pop(training_id, None)

    @staticmethod
    def _defender_score(position: Position, move: FastMove) -> tuple[int, int, int, str]:
        """Prefer central, mobile, non-checking defensive replies deterministically."""
        child = FastPosition.from_fen(position.fen).apply(move)
        king = child.king_square(position.turn == -1 and "b" or "w")
        # After apply, ``position.turn`` was the defender.  Larger centre distance score is better.
        if king < 0:
            center = -99
        else:
            file_, rank = king % 8, king // 8
            edge_distance = min(file_, 7 - file_, rank, 7 - rank)
            center = edge_distance
        mobility = len(child.legal_moves())
        checked_penalty = -int(child.in_check(child.turn))
        return (center, mobility, checked_penalty, move.uci)

    def _automatic_defence(self, session: TrainingSession) -> tuple[dict[str, Any] | None, str | None]:
        fast = FastPosition.from_fen(session.position.fen)
        candidates = sorted(fast.legal_moves(), key=lambda move: self._defender_score(session.position, move), reverse=True)
        rejected: list[str] = []
        for candidate in candidates:
            model_move = self._fast_to_model(candidate)
            transition, receipt = self.gate.validate_move(session.position, model_move)
            if not receipt.accepted:
                rejected.append(candidate.uci)
                continue
            san = render_san(self.gate, transition)
            session.position = transition.after
            row = {
                "ply": len(session.history) + 1,
                "actor": "defender",
                "uci": model_move.uci,
                "san": san,
                "fen": session.position.fen,
                "outcome": receipt.outcome,
                "query_sha256": receipt.query_sha256,
            }
            session.history.append(row)
            return receipt.to_dict(include_source=True), None
        if candidates:
            return None, "宿主侧候选与 Litex 门禁出现差异；全部自动防守候选均被拒绝：" + ", ".join(rejected[:8])
        return None, None

    def play(self, training_id: str, move: Move) -> dict[str, Any]:
        with self._lock:
            try:
                session = self._sessions[training_id]
            except KeyError as exc:
                raise KeyError(f"unknown endgame training session: {training_id}") from exc
        with session.lock:
            before_public = self._public(session)
            if before_public["finished"]:
                raise ValueError("this endgame lesson is already finished")
            learner_is_white = session.lesson.learner_side == "w"
            if (session.position.turn == 1) != learner_is_white:
                raise ValueError("it is not the learner's turn")

            transition, receipt = self.gate.validate_move(session.position, move)
            receipts = [receipt.to_dict(include_source=True)]
            if not receipt.accepted:
                payload = self._public(session, last_receipts=receipts)
                payload["accepted"] = False
                return payload

            san = render_san(self.gate, transition)
            session.position = transition.after
            session.history.append(
                {
                    "ply": len(session.history) + 1,
                    "actor": "learner",
                    "uci": move.uci,
                    "san": san,
                    "fen": session.position.fen,
                    "outcome": receipt.outcome,
                    "query_sha256": receipt.query_sha256,
                }
            )
            analysis = self._status(session.position)
            finished, _ = self._finished(session, analysis)
            if not finished:
                defence_receipt, warning = self._automatic_defence(session)
                session.warning = warning
                if defence_receipt is not None:
                    receipts.append(defence_receipt)

            payload = self._public(session, last_receipts=receipts)
            payload["accepted"] = True
            return payload


def ranked_defender_moves(position: Position, lesson_id: str) -> list[Move]:
    """Return deterministic defensive candidates for a workbench lesson.

    The returned list is only a proposal order.  The API must submit each
    candidate through ``SessionStore.play``; this helper never authorizes or
    commits a move.  It intentionally avoids tablebase/optimal-play claims.
    """

    try:
        item = LESSONS[lesson_id]
    except KeyError as exc:
        raise KeyError(f"unknown endgame lesson: {lesson_id}") from exc
    learner_side = 1 if item.learner_side == "w" else -1
    if position.turn == learner_side:
        raise ValueError("it is the learner's turn; no automatic defence is due")
    fast = FastPosition.from_fen(position.fen)

    def score(move: FastMove) -> tuple[int, int, int, int, str]:
        captured = fast.board[move.target]
        captured_value = {"q": 9, "r": 5, "b": 3, "n": 3, "p": 1}.get(captured.lower(), 0) if captured else 0
        child = fast.apply(move)
        defender_king = child.king_square("w" if position.turn == 1 else "b")
        if defender_king < 0:
            edge_distance = -99
        else:
            file_, rank = defender_king % 8, defender_king // 8
            edge_distance = min(file_, 7 - file_, rank, 7 - rank)
        mobility = len(child.legal_moves())
        avoids_check = int(not child.in_check(child.turn))
        return (captured_value, edge_distance, mobility, avoids_check, move.uci)

    return [Move.from_uci(move.uci) for move in sorted(fast.legal_moves(), key=score, reverse=True)]


def list_lessons() -> list[dict[str, Any]]:
    """Compatibility catalogue helper used by non-interactive clients."""
    return [item.json() for item in LESSONS.values()]


def lesson(lesson_id: str) -> dict[str, Any]:
    if lesson_id not in LESSONS:
        raise KeyError(lesson_id)
    item = LESSONS[lesson_id]
    position = Position.from_fen(item.fen)
    return {**item.json(), "analysis": {**analyze_fen(item.fen), "dead_position": PositionStatusAnalyzer.known_dead_position(position)}}


def feedback(fen: str) -> dict[str, Any]:
    position = Position.from_fen(fen)
    analysis = {**analyze_fen(fen), "dead_position": PositionStatusAnalyzer.known_dead_position(position)}
    distance, edge = EndgameTrainer._king_metrics(position)
    return {
        **analysis,
        "king_distance": distance,
        "defender_edge_distance": edge,
        "hint": EndgameTrainer._hint(position, analysis),
    }
