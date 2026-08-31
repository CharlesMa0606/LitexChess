from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from litex_chess.candidate import apply_candidate
from litex_chess.model import GateReceipt, Move, Position


@dataclass
class ScriptedGate:
    accepted_uci: set[str]

    def validate_move(self, position: Position, move: Move):
        transition = apply_candidate(position, move)
        accepted = move.uci in self.accepted_uci
        receipt = GateReceipt(
            accepted=accepted,
            engine="test-scripted-litex",
            query_sha256=move.uci,
            elapsed_ms=0.1,
            reason="scripted success" if accepted else "scripted rejection",
            results=[{"result": "success" if accepted else "error", "stmt": move.uci}],
        )
        return transition, receipt

    def validate_position(self, position: Position):
        return GateReceipt(True, "test-scripted-litex", position.fen, 0.1, "ok", [{"result": "success"}])

    def health(self) -> dict[str, Any]:
        return {"ready": True}

    def close(self) -> None:
        return None


@pytest.fixture
def scripted_gate():
    return ScriptedGate({
        "e2e4", "e7e5", "g1f3", "b8c6", "c7c5",
        "f1c4", "g8f6", "d2d3", "f8c5", "e1g1",
        "b1c3", "d7d6", "f8e7", "e8g8",
    })
