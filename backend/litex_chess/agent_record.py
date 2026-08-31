"""Agent-facing Litex record for a single verified chess transition.

The record is deliberately small and close to ordinary move notation.  It is
prepended to the same Litex transaction as the detailed certificate, so it is
not an independent or weaker legality path.
"""
from __future__ import annotations

from dataclasses import dataclass

FILES = "abcdefgh"
OUTCOME_CODES = {
    "ongoing": 0,
    "check": 1,
    "checkmate": 2,
    "stalemate": 3,
    "unclassified": 4,
}


def _square_index(square: str) -> int:
    text = square.lower().strip()
    if len(text) != 2 or text[0] not in FILES or text[1] not in "12345678":
        raise ValueError(f"invalid square: {square!r}")
    return (int(text[1]) - 1) * 8 + FILES.index(text[0])


@dataclass(frozen=True)
class AgentRecord:
    source: str
    target: str
    promotion: int
    outcome: str
    checker_count: int
    legal_reply_count: int
    uci: str

    def litex(self) -> str:
        source = self.source.lower()
        target = self.target.lower()
        if self.outcome not in OUTCOME_CODES:
            raise ValueError(f"unsupported outcome: {self.outcome!r}")
        lines = [
            "# [agent-record:start]",
            "# Agent-facing summary checked in the same fail-closed transaction",
            "# as the detailed move certificate below.",
            f"have {source} Z = {_square_index(source)}",
        ]
        if target != source:
            lines.append(f"have {target} Z = {_square_index(target)}")
        lines.extend(
            [
                f"have {self.outcome} Z = {OUTCOME_CODES[self.outcome]}",
                f"by def $square({FILES.index(source[0]) + 1}, {int(source[1])}, {source})",
                f"by def $square({FILES.index(target[0]) + 1}, {int(target[1])}, {target})",
                f"by def $move({source}, {target})",
                f"by def $promotion_choice({int(self.promotion)})",
                f"by def $result({self.outcome})",
                (
                    f"by def $result_witness({self.outcome}, "
                    f"{int(self.checker_count)}, {int(self.legal_reply_count)})"
                ),
                (
                    f"# move={self.uci}; result={self.outcome}; "
                    f"checkers={int(self.checker_count)}; "
                    f"legal_replies={int(self.legal_reply_count)}"
                ),
                "# [agent-record:end]",
            ]
        )
        return "\n".join(lines)


def make_agent_record(
    source: str,
    target: str,
    *,
    promotion: int = 0,
    outcome: str = "unclassified",
    checker_count: int = -1,
    legal_reply_count: int = -1,
    uci: str | None = None,
) -> AgentRecord:
    source = source.lower().strip()
    target = target.lower().strip()
    _square_index(source)
    _square_index(target)
    if promotion not in {0, 2, 3, 4, 5}:
        raise ValueError("promotion must be 0, 2, 3, 4, or 5")
    return AgentRecord(
        source=source,
        target=target,
        promotion=int(promotion),
        outcome=outcome,
        checker_count=int(checker_count),
        legal_reply_count=int(legal_reply_count),
        uci=(uci or source + target).lower(),
    )
