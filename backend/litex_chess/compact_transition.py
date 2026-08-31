"""Exact sparse board-transition certificates.

A legal chess move changes only two, three, or four squares.  The runtime keeps
``Position.board`` as an ordinary immutable 64-cell tuple for rendering and
FEN, but proves the successor with a canonical sparse delta rather than 64
repeated equalities.

The global guard is an injective base-16 encoding, not a probabilistic hash::

    code(board) = sum((piece[i] + 6) * 16**i, i=0..63)

Piece codes lie in ``[-6, 6]``, hence every digit lies in ``[0, 12]`` and the
base-16 expansion uniquely identifies the full board.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any, Sequence

BASE = 16
EMPTY_SHIFT = 6
BOARD_SIZE = 64
PIECE_FROM_FEN = {
    "P": 1,
    "N": 2,
    "B": 3,
    "R": 4,
    "Q": 5,
    "K": 6,
    "p": -1,
    "n": -2,
    "b": -3,
    "r": -4,
    "q": -5,
    "k": -6,
}


def normalize_mode(mode: str | None = None) -> str:
    """Return the sole production transition mode.

    ``compact`` remains accepted as a compatibility spelling, but no runtime
    path can silently re-enable the retired 64-cell proof.
    """

    selected = (mode or "sparse").strip().lower()
    if selected in {"sparse", "compact"}:
        return "sparse"
    raise ValueError("board transition mode must be 'sparse'")


@dataclass(frozen=True, slots=True)
class SquareEdit:
    index: int
    before: int
    after: int

    def __post_init__(self) -> None:
        if not 0 <= self.index < BOARD_SIZE:
            raise ValueError(f"square index out of range: {self.index}")
        if not -6 <= self.before <= 6 or not -6 <= self.after <= 6:
            raise ValueError("piece codes must lie in [-6, 6]")
        if self.before == self.after:
            raise ValueError("a sparse edit must change the square")

    @property
    def weight(self) -> int:
        return BASE**self.index

    @property
    def contribution(self) -> int:
        return (self.after - self.before) * self.weight

    @property
    def algebraic(self) -> str:
        return f"{chr(ord('a') + self.index % 8)}{self.index // 8 + 1}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "square": self.algebraic,
            "before": self.before,
            "after": self.after,
            "weight": self.weight,
            "contribution": self.contribution,
        }


@dataclass(frozen=True, slots=True)
class SparseBoardDelta:
    before_code: int
    expected_after_code: int
    actual_after_code: int
    edits: tuple[SquareEdit, ...]
    duplicate_count: int = 0
    before_mismatch_count: int = 0
    after_mismatch_count: int = 0

    @property
    def delta_code(self) -> int:
        return sum(edit.contribution for edit in self.edits)

    @property
    def exact(self) -> bool:
        return (
            2 <= len(self.edits) <= 4
            and self.duplicate_count == 0
            and self.before_mismatch_count == 0
            and self.after_mismatch_count == 0
            and self.expected_after_code == self.before_code + self.delta_code
            and self.actual_after_code == self.expected_after_code
        )

    @property
    def after_code(self) -> int:
        return self.expected_after_code

    def apply(self, board: Sequence[int]) -> tuple[int, ...]:
        if len(board) != BOARD_SIZE:
            raise ValueError("board must contain 64 cells")
        out = [int(value) for value in board]
        seen: set[int] = set()
        for edit in self.edits:
            if edit.index in seen:
                raise ValueError(f"duplicate sparse edit at {edit.algebraic}")
            seen.add(edit.index)
            if out[edit.index] != edit.before:
                raise ValueError(
                    f"edit {edit.algebraic} expects {edit.before}, found {out[edit.index]}"
                )
            out[edit.index] = edit.after
        return tuple(out)

    def to_dict(self, *, mode: str = "sparse") -> dict[str, Any]:
        normalize_mode(mode)
        return {
            "mode": "sparse",
            "encoding": "injective-base16",
            "edit_count": len(self.edits),
            "edits": [edit.to_dict() for edit in self.edits],
            "changed_squares": [edit.algebraic for edit in self.edits],
            "legacy_cell_comparisons": 0,
            "before_code": self.before_code,
            "expected_after_code": self.expected_after_code,
            "actual_after_code": self.actual_after_code,
            "before_code_hex": hex(self.before_code),
            "expected_after_code_hex": hex(self.expected_after_code),
            "actual_after_code_hex": hex(self.actual_after_code),
            "delta_code": self.delta_code,
            "duplicate_count": self.duplicate_count,
            "before_mismatch_count": self.before_mismatch_count,
            "after_mismatch_count": self.after_mismatch_count,
            "exact": self.exact,
        }

    summary = to_dict


def encode_board(board: Sequence[int]) -> int:
    if len(board) != BOARD_SIZE:
        raise ValueError(f"board must contain 64 cells, got {len(board)}")
    code = 0
    for index, raw in enumerate(board):
        piece = int(raw)
        if not -6 <= piece <= 6:
            raise ValueError(f"invalid piece code {piece} at index {index}")
        code += (piece + EMPTY_SHIFT) * (BASE**index)
    return code


def decode_board(code: int) -> tuple[int, ...]:
    if code < 0:
        raise ValueError("packed board code must be non-negative")
    value = int(code)
    out: list[int] = []
    for _ in range(BOARD_SIZE):
        digit = value % BASE
        if digit > 12:
            raise ValueError(f"packed board contains invalid digit {digit}")
        out.append(digit - EMPTY_SHIFT)
        value //= BASE
    if value:
        raise ValueError("packed board has more than 64 digits")
    return tuple(out)


def derive_delta(
    before: Sequence[int],
    expected_after: Sequence[int],
    actual_after: Sequence[int] | None = None,
) -> SparseBoardDelta:
    before_board = tuple(int(value) for value in before)
    expected_board = tuple(int(value) for value in expected_after)
    actual_board = expected_board if actual_after is None else tuple(int(value) for value in actual_after)
    if not (len(before_board) == len(expected_board) == len(actual_board) == BOARD_SIZE):
        raise ValueError("all boards must contain exactly 64 cells")

    edits = tuple(
        SquareEdit(index, old, new)
        for index, (old, new) in enumerate(zip(before_board, expected_board))
        if old != new
    )
    duplicate_count = len(edits) - len({edit.index for edit in edits})
    before_mismatch_count = sum(before_board[e.index] != e.before for e in edits)
    rebuilt = before_board
    if not duplicate_count:
        probe = SparseBoardDelta(
            encode_board(before_board),
            encode_board(expected_board),
            encode_board(actual_board),
            edits,
        )
        rebuilt = probe.apply(before_board)
    after_mismatch_count = sum(a != e for a, e in zip(actual_board, expected_board))
    after_mismatch_count += sum(a != e for a, e in zip(rebuilt, expected_board))

    return SparseBoardDelta(
        before_code=encode_board(before_board),
        expected_after_code=encode_board(expected_board),
        actual_after_code=encode_board(actual_board),
        edits=edits,
        duplicate_count=duplicate_count,
        before_mismatch_count=int(before_mismatch_count),
        after_mismatch_count=int(after_mismatch_count),
    )


def sparse_litex_lines(
    before: Sequence[int],
    expected_after: Sequence[int],
    actual_after: Sequence[int],
) -> tuple[list[str], SparseBoardDelta]:
    delta = derive_delta(before, expected_after, actual_after)
    contributions = [edit.contribution for edit in delta.edits][:4]
    padded = contributions + [0] * (4 - len(contributions))
    lines = [
        "# Sparse successor: only changed squares are listed.",
        f"# edits={len(delta.edits)}; squares={','.join(e.algebraic for e in delta.edits) or 'none'}",
        f"# exact-board-code: {hex(delta.before_code)} -> {hex(delta.actual_after_code)}",
    ]
    for edit in delta.edits:
        lines.append(
            "by def $sparse_square_edit("
            f"{edit.index}, {edit.before}, {edit.after}, {edit.weight}, {edit.contribution})"
        )
    lines.append(
        "by def $sparse_board_transition("
        f"{delta.before_code}, {delta.actual_after_code}, "
        f"{padded[0]}, {padded[1]}, {padded[2]}, {padded[3]}, "
        f"{len(delta.edits)}, {delta.duplicate_count}, "
        f"{delta.before_mismatch_count}, {delta.after_mismatch_count})"
    )
    return lines, delta


def board_from_fen(fen: str) -> tuple[int, ...]:
    placement = fen.strip().split()[0]
    ranks = placement.split("/")
    if len(ranks) != 8:
        raise ValueError(f"invalid FEN placement: {placement!r}")
    board = [0] * BOARD_SIZE
    for fen_rank, token in enumerate(ranks):
        file_index = 0
        rank_index = 7 - fen_rank
        for char in token:
            if char.isdigit():
                file_index += int(char)
            elif char in PIECE_FROM_FEN and file_index < 8:
                board[rank_index * 8 + file_index] = PIECE_FROM_FEN[char]
                file_index += 1
            else:
                raise ValueError(f"invalid FEN rank: {token!r}")
        if file_index != 8:
            raise ValueError(f"invalid FEN rank width: {token!r}")
    return tuple(board)

# ---------------------------------------------------------------------------
# Compatibility transformer for old 64-cell query traces
# ---------------------------------------------------------------------------
# Production queries are generated directly in sparse form by query.py.  This
# transformer remains solely for replaying pre-v0.8 traces and for differential
# audits.  It is deliberately explicit: no import-time monkeypatching and no
# recursive wrapper installation.

AUDIT_MODES = {"compact", "sparse", "dual", "legacy"}
_FEN_RE = re.compile(
    r"([prnbqkPRNBQK1-8/]+\s+[wb]\s+(?:-|K?Q?k?q?)\s+"
    r"(?:-|[a-h][1-8])\s+\d+\s+\d+)"
)


def _fen_candidates(source: str) -> list[str]:
    out: list[str] = []
    for match in _FEN_RE.finditer(source):
        fen = " ".join(match.group(1).split())
        if fen not in out:
            out.append(fen)
    return out


def _call_spans(source: str, needle: str = "board_rank_transition") -> list[tuple[int, int]]:
    """Locate complete legacy calls, including multiline argument lists."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    while True:
        pos = source.find(needle, cursor)
        if pos < 0:
            break
        line_start = source.rfind("\n", 0, pos) + 1
        open_pos = source.find("(", pos)
        if open_pos < 0:
            cursor = pos + len(needle)
            continue
        depth = 0
        quote: str | None = None
        escape = False
        end: int | None = None
        for index in range(open_pos, len(source)):
            char = source[index]
            if quote is not None:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            cursor = pos + len(needle)
            continue
        while end < len(source) and source[end] in " \t":
            end += 1
        if end < len(source) and source[end] == "\n":
            end += 1
        spans.append((line_start, end))
        cursor = end
    return spans


def _namespace_and_style(source: str) -> tuple[str, str]:
    match = re.search(
        r"(?m)^\s*(by\s+def\s+)?\$([A-Za-z_][\w:]*)board_rank_transition\s*\(",
        source,
    )
    if match is None:
        return "chess_rules::", "by def "
    return match.group(2), "by def " if match.group(1) else ""


def _insert_before_contract(source: str, block: str) -> str:
    positions: list[int] = []
    for needle in ("metadata_transition", "position_transition", "legal_transition"):
        pos = source.find(needle)
        if pos >= 0:
            positions.append(source.rfind("\n", 0, pos) + 1)
    insertion = min(positions) if positions else len(source)
    separator = "" if insertion == 0 or source[:insertion].endswith("\n") else "\n"
    return source[:insertion] + separator + block + source[insertion:]


def _sparse_block(before: Sequence[int], after: Sequence[int], *, namespaced: bool) -> str:
    delta = derive_delta(before, after)
    if not delta.exact:
        raise ValueError(
            "legacy query does not describe an ordinary 2-4 square chess transition"
        )
    prefix = "chess_rules::" if namespaced else ""
    style = "by def "
    lines = [
        "# ── 精确稀疏棋盘变更证书 / exact sparse board delta ──",
        "# 仅列出实际变化格；未列出的格由不可变棋盘更新语义保持。",
        (
            f"# edits={len(delta.edits)}; "
            f"squares={','.join(edit.algebraic for edit in delta.edits)}"
        ),
        f"# before_code={hex(delta.before_code)}",
        f"# after_code={hex(delta.actual_after_code)}",
    ]
    contributions: list[int] = []
    for edit in delta.edits:
        contributions.append(edit.contribution)
        lines.append(
            f"{style}${prefix}sparse_square_edit("
            f"{edit.index}, {edit.before}, {edit.after}, "
            f"{edit.weight}, {edit.contribution})"
        )
    padded = contributions + [0] * (4 - len(contributions))
    lines.append(
        f"{style}${prefix}sparse_board_transition("
        f"{delta.before_code}, {delta.actual_after_code}, "
        f"{padded[0]}, {padded[1]}, {padded[2]}, {padded[3]}, "
        f"{len(delta.edits)}, {delta.duplicate_count}, "
        f"{delta.before_mismatch_count}, {delta.after_mismatch_count})"
    )
    lines.append("# ── 稀疏棋盘变更证书结束 ──")
    return "\n".join(lines) + "\n"


def compact_query_source(
    source: str,
    *,
    before: Sequence[int] | None = None,
    after: Sequence[int] | None = None,
    mode: str | None = None,
) -> str:
    """Convert a legacy rank-by-rank query to the sparse exact certificate.

    ``compact`` and ``sparse`` remove the eight legacy calls; ``dual`` keeps
    them as an optional differential audit; ``legacy`` returns the source
    unchanged.  Already-sparse input is returned byte-for-byte, so the function
    is idempotent.
    """
    selected = (mode or os.getenv("LITEX_BOARD_TRANSITION_MODE", "compact")).strip().lower()
    if selected not in AUDIT_MODES:
        raise ValueError(f"unsupported board transition audit mode: {selected!r}")
    if selected == "legacy" or "board_rank_transition" not in source:
        return source
    if "sparse_board_transition" in source:
        return source

    if before is None or after is None:
        fens = _fen_candidates(source)
        if len(fens) < 2:
            return source
        before = board_from_fen(fens[0])
        after = board_from_fen(fens[1])

    namespace, _ = _namespace_and_style(source)
    block = _sparse_block(before, after, namespaced=bool(namespace))
    if namespace != "chess_rules::":
        block = block.replace("$chess_rules::", f"${namespace}")

    if selected == "dual":
        return _insert_before_contract(source, block)

    result = source
    for start, end in reversed(_call_spans(result)):
        result = result[:start] + result[end:]
    return _insert_before_contract(result, block)

# ---------------------------------------------------------------------------
# Compatibility transformer for archived pre-v0.8 query fixtures.
# ---------------------------------------------------------------------------
# Production queries are built directly with ``sparse_litex_lines`` and never
# need this transformer.  It remains intentionally small so old fixtures can be
# compared with the sparse representation during regression tests.
import re as _re

_FEN_COMMENT = _re.compile(r"(?m)^#\s*(before_fen|after_fen)\s*:\s*(.+?)\s*$")
_RANK_LINE = _re.compile(
    r"(?m)^.*\bboard_rank_transition\s*\([^\n]*\)\s*$"
)


def _compact_query_source_impl(
    source: str,
    *,
    before: str | Sequence[int] | None = None,
    after: str | Sequence[int] | None = None,
    mode: str | None = None,
) -> str:
    """Convert an archived 64-cell audit query into a sparse certificate.

    ``compact``/``sparse`` removes legacy rank statements, ``dual`` retains
    them after adding the sparse certificate, and ``legacy`` returns the input
    unchanged.  The function is idempotent.
    """
    selected = (mode or "compact").strip().lower()
    if selected == "sparse":
        selected = "compact"
    if selected not in {"compact", "dual", "legacy"}:
        raise ValueError("mode must be compact, sparse, dual, or legacy")
    if selected == "legacy":
        return source
    if "sparse_board_transition" in source:
        if selected == "compact":
            return _RANK_LINE.sub("", source).replace("\n\n\n", "\n\n")
        return source

    comments = {key: value.strip() for key, value in _FEN_COMMENT.findall(source)}

    def coerce(value: str | Sequence[int] | None, key: str) -> tuple[int, ...]:
        if value is None:
            value = comments.get(key)
        if value is None:
            raise ValueError(f"{key} is required when converting a legacy query")
        if isinstance(value, str):
            return board_from_fen(value)
        return tuple(int(item) for item in value)

    before_board = coerce(before, "before_fen")
    after_board = coerce(after, "after_fen")
    lines, _ = sparse_litex_lines(before_board, after_board, after_board)
    sparse_block = "\n".join(lines)

    match = _RANK_LINE.search(source)
    if match:
        insert_at = match.start()
        prefix = source[:insert_at].rstrip()
        legacy_block = "\n".join(_RANK_LINE.findall(source))
        suffix = _RANK_LINE.sub("", source[match.end():]).strip("\n")
        parts = [prefix, sparse_block]
        if selected == "dual" and legacy_block:
            parts.extend(["# Optional legacy differential audit", legacy_block])
        if suffix:
            parts.append(suffix)
        return "\n".join(part for part in parts if part).rstrip() + "\n"

    return source.rstrip() + "\n" + sparse_block + "\n"


def compact_query_source(
    source: str,
    *,
    before: str | Sequence[int] | None = None,
    after: str | Sequence[int] | None = None,
    mode: str | None = None,
) -> str:
    return _compact_query_source_impl(source, before=before, after=after, mode=mode)
