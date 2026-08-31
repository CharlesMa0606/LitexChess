from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any

from .game_tree import GameTree
from .litex_gate import Gate
from .model import Move, Position
from .pgn import import_pgn
from .presentation import render_san


@dataclass(slots=True)
class StudySession:
    id: str
    tree: GameTree
    lock: threading.RLock


class SessionStore:
    def __init__(self, gate: Gate) -> None:
        self.gate = gate
        self._sessions: dict[str, StudySession] = {}
        self._lock = threading.RLock()

    def create(
        self,
        position: Position,
        validate_root: bool = False,
        headers: dict[str, str] | None = None,
    ) -> tuple[StudySession, dict[str, Any] | None]:
        receipt_payload = None
        if validate_root:
            receipt = self.gate.validate_position(position)
            receipt_payload = receipt.to_dict(include_source=True)
            if not receipt.accepted:
                raise ValueError(
                    "Litex did not certify the root position: "
                    + "; ".join(receipt.diagnostics[:4])
                )
        session_id = uuid.uuid4().hex[:16]
        session = StudySession(
            id=session_id,
            tree=GameTree(position, headers=headers),
            lock=threading.RLock(),
        )
        with self._lock:
            self._sessions[session_id] = session
        return session, receipt_payload

    def get(self, session_id: str) -> StudySession:
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise KeyError(f"unknown session: {session_id}") from exc

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def play(self, session_id: str, parent_id: str, move: Move) -> tuple[dict[str, Any], dict[str, Any]]:
        session = self.get(session_id)
        with session.lock:
            parent = session.tree.nodes.get(parent_id)
            if parent is None:
                raise KeyError(f"unknown node: {parent_id}")
            transition, receipt = self.gate.validate_move(parent.position, move)
            if not receipt.accepted:
                return session.tree.to_dict(), receipt.to_dict(include_source=True)
            san = render_san(self.gate, transition)
            session.tree.add_move(
                parent_id,
                move,
                san,
                transition.after,
                receipt,
            )
            # Keep the ordinary PGN result header aligned with the verified
            # terminal status carried by the same move certificate.  The side
            # to move in the parent is the mover.
            if receipt.outcome == "checkmate":
                session.tree.headers["Result"] = "1-0" if parent.position.turn == 1 else "0-1"
            elif receipt.outcome == "stalemate":
                session.tree.headers["Result"] = "1/2-1/2"
            return session.tree.to_dict(), receipt.to_dict(include_source=True)

    def goto(self, session_id: str, node_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        with session.lock:
            session.tree.goto(node_id)
            return session.tree.to_dict()

    def node_receipt(self, session_id: str, node_id: str) -> dict[str, Any] | None:
        """Return the accepted Litex receipt stored on one game-tree node.

        The root has no move receipt.  Keeping this accessor separate from the
        ordinary tree payload prevents every navigation response from carrying
        a potentially large generated Litex query for every node.
        """

        session = self.get(session_id)
        with session.lock:
            node = session.tree.nodes.get(node_id)
            if node is None:
                raise KeyError(f"unknown node: {node_id}")
            if node.receipt is None:
                return None
            return node.receipt.to_dict(include_source=True)

    def import_text(
        self,
        pgn: str,
        validate_root: bool = False,
    ) -> StudySession:
        tree = import_pgn(self.gate, pgn, validate_root=validate_root)
        session_id = uuid.uuid4().hex[:16]
        session = StudySession(session_id, tree, threading.RLock())
        with self._lock:
            self._sessions[session_id] = session
        return session
