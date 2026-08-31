from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .game_tree import GameTree
from .litex_gate import Gate
from .model import (
    BISHOP,
    KING,
    KNIGHT,
    PAWN,
    QUEEN,
    ROOK,
    Move,
    Position,
    PositionFormatError,
    FILES,
    PROMOTION_TO_CODE,
    START_FEN,
)
from .presentation import render_san


class PGNImportError(ValueError):
    pass


PIECE_KIND = {"N": KNIGHT, "B": BISHOP, "R": ROOK, "Q": QUEEN, "K": KING}
RESULT_TOKENS = {"1-0", "0-1", "1/2-1/2", "*"}
HEADER_RE = re.compile(r'^\s*\[([A-Za-z0-9_]+)\s+"((?:\\.|[^"])*)"\]\s*$', re.M)
TOKEN_RE = re.compile(r"\{[^}]*\}|;[^\n]*|\(|\)|\$\d+|[^\s(){}]+")
MOVE_NUMBER_RE = re.compile(r"^\d+\.(?:\.\.)?$")
ANNOTATION_RE = re.compile(r"[!?]+$")


@dataclass(frozen=True, slots=True)
class SANPattern:
    raw: str
    piece_kind: int
    to_file: int
    to_rank: int
    capture: bool
    from_file: int | None = None
    from_rank: int | None = None
    promotion: int = 0
    castle: str | None = None


def _unescape_header(value: str) -> str:
    return value.replace(r'\"', '"').replace(r"\\", "\\")


def parse_headers(pgn: str) -> dict[str, str]:
    return {key: _unescape_header(value) for key, value in HEADER_RE.findall(pgn)}


def tokenize_movetext(pgn: str) -> list[str]:
    without_headers = HEADER_RE.sub("", pgn)
    return TOKEN_RE.findall(without_headers)


def parse_san_pattern(token: str, position: Position) -> SANPattern:
    raw = token
    token = ANNOTATION_RE.sub("", token.strip())
    token = token.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    token = re.sub(r"[+#]+$", "", token)
    if token in {"O-O", "O-O-O"}:
        rank = 1 if position.turn == 1 else 8
        return SANPattern(
            raw=raw,
            piece_kind=KING,
            to_file=7 if token == "O-O" else 3,
            to_rank=rank,
            capture=False,
            from_file=5,
            from_rank=rank,
            castle=token,
        )

    promotion = 0
    promo_match = re.search(r"=?([QRBN])$", token)
    if promo_match:
        promotion = PROMOTION_TO_CODE[promo_match.group(1).lower()]
        token = token[: promo_match.start()]

    if len(token) < 2 or token[-2] not in FILES or token[-1] not in "12345678":
        raise PGNImportError(f"unsupported or malformed SAN token: {raw!r}")
    to_file = FILES.index(token[-2]) + 1
    to_rank = int(token[-1])
    prefix = token[:-2]
    capture = "x" in prefix
    prefix = prefix.replace("x", "")

    piece_kind = PAWN
    if prefix and prefix[0] in PIECE_KIND:
        piece_kind = PIECE_KIND[prefix[0]]
        prefix = prefix[1:]

    from_file = None
    from_rank = None
    if len(prefix) > 2:
        raise PGNImportError(f"unsupported SAN disambiguation: {raw!r}")
    for char in prefix:
        if char in FILES:
            if from_file is not None:
                raise PGNImportError(f"duplicate file disambiguation: {raw!r}")
            from_file = FILES.index(char) + 1
        elif char in "12345678":
            if from_rank is not None:
                raise PGNImportError(f"duplicate rank disambiguation: {raw!r}")
            from_rank = int(char)
        else:
            raise PGNImportError(f"unsupported SAN prefix: {raw!r}")

    if piece_kind == PAWN and capture and from_file is None:
        raise PGNImportError(f"pawn capture SAN must include origin file: {raw!r}")

    return SANPattern(
        raw=raw,
        piece_kind=piece_kind,
        to_file=to_file,
        to_rank=to_rank,
        capture=capture,
        from_file=from_file,
        from_rank=from_rank,
        promotion=promotion,
    )


def resolve_san(gate: Gate, position: Position, token: str) -> tuple[Move, object, object]:
    pattern = parse_san_pattern(token, position)
    side = position.turn
    candidates: list[tuple[Move, object, object]] = []
    diagnostics: list[str] = []

    if pattern.castle:
        origins = [(pattern.from_file or 5, pattern.from_rank or (1 if side == 1 else 8))]
    else:
        origins = []
        for rank in range(1, 9):
            for file in range(1, 9):
                if pattern.from_file is not None and file != pattern.from_file:
                    continue
                if pattern.from_rank is not None and rank != pattern.from_rank:
                    continue
                if position.piece_at(file, rank) == side * pattern.piece_kind:
                    origins.append((file, rank))

    for from_file, from_rank in origins:
        try:
            move = Move(
                from_file,
                from_rank,
                pattern.to_file,
                pattern.to_rank,
                pattern.promotion,
            )
        except PositionFormatError:
            continue
        transition, receipt = gate.validate_move(position, move)
        if transition.is_capture != pattern.capture:
            continue
        if receipt.accepted:
            candidates.append((move, transition, receipt))
        elif receipt.diagnostics:
            diagnostics.extend(receipt.diagnostics[:1])

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        detail = "; ".join(diagnostics[:4])
        raise PGNImportError(
            f"Litex rejected SAN {token!r} from {position.fen}"
            + (f": {detail}" if detail else "")
        )
    raise PGNImportError(
        f"SAN {token!r} remains ambiguous after Litex validation: "
        + ", ".join(item[0].uci for item in candidates)
    )


def import_pgn(gate: Gate, pgn: str, validate_root: bool = True) -> GameTree:
    headers = parse_headers(pgn)
    root_fen = headers.get("FEN", START_FEN)
    try:
        root_position = Position.from_fen(root_fen)
    except PositionFormatError as exc:
        raise PGNImportError(f"invalid PGN root FEN: {exc}") from exc
    if validate_root:
        receipt = gate.validate_position(root_position)
        if not receipt.accepted:
            raise PGNImportError(
                "Litex did not certify the PGN root position: "
                + "; ".join(receipt.diagnostics[:4])
            )

    tree = GameTree(root_position, headers=headers)
    current_id = tree.root_id
    last_move_id: str | None = None
    resume_stack: list[tuple[str, str | None]] = []

    for token in tokenize_movetext(pgn):
        if token.startswith(";"):
            continue
        if token.startswith("{"):
            if last_move_id is not None:
                tree.nodes[last_move_id].comment = token[1:-1].strip()
            continue
        if token.startswith("$"):
            if last_move_id is not None:
                tree.nodes[last_move_id].nags.append(token)
            continue
        if token == "(":
            if last_move_id is None:
                raise PGNImportError("variation cannot start before a move")
            branch_parent = tree.nodes[last_move_id].parent_id
            if branch_parent is None:
                branch_parent = tree.root_id
            resume_stack.append((current_id, last_move_id))
            current_id = branch_parent
            last_move_id = None
            continue
        if token == ")":
            if not resume_stack:
                raise PGNImportError("unmatched closing parenthesis in PGN")
            current_id, last_move_id = resume_stack.pop()
            continue
        if token in RESULT_TOKENS:
            tree.headers["Result"] = token
            continue
        if MOVE_NUMBER_RE.match(token) or re.match(r"^\d+\.{1,3}.*$", token) and token.rstrip(".").isdigit():
            continue
        if token.lower() in {"e.p.", "ep"}:
            continue

        parent = tree.nodes[current_id]
        move, transition, receipt = resolve_san(gate, parent.position, token)
        node = tree.add_move(
            current_id,
            move,
            token,
            transition.after,
            receipt,
        )
        current_id = node.id
        last_move_id = node.id

    if resume_stack:
        raise PGNImportError("unclosed variation in PGN")
    tree.current_id = current_id
    return tree


# v0.8 terminal suffix correction: an already constructed SAN ending
# in '+' becomes '#' exactly when the resulting FEN is checkmate.
def _install_mate_suffix_wrappers():
    import functools as _functools
    from .fast_state import analyze_fen as _analyze_fen

    def _find_fens(value, out, seen):
        oid=id(value)
        if oid in seen: return
        seen.add(oid)
        fen=getattr(value, 'fen', None)
        if callable(fen):
            try: fen=fen()
            except TypeError: fen=None
        if isinstance(fen,str) and fen.count('/')==7 and fen not in out:
            out.append(fen)
        if isinstance(value,dict):
            for x in value.values(): _find_fens(x,out,seen)
        elif isinstance(value,(tuple,list)):
            for x in value: _find_fens(x,out,seen)

    def _wrap(fn):
        @_functools.wraps(fn)
        def inner(*args,**kwargs):
            result=fn(*args,**kwargs)
            if not isinstance(result,str) or not result.endswith('+'):
                return result
            fens=[]; _find_fens(args,fens,set()); _find_fens(kwargs,fens,set())
            if fens:
                try:
                    if _analyze_fen(fens[-1]).get('status')=='checkmate':
                        return result[:-1]+'#'
                except Exception:
                    pass
            return result
        return inner

    for _name in SAN_FUNCTION_NAMES:
        _fn=globals().get(_name)
        if callable(_fn): globals()[_name]=_wrap(_fn)

SAN_FUNCTION_NAMES = ['parse_san_pattern', 'resolve_san']
_install_mate_suffix_wrappers()

# v0.8: SAN suffix is a position result, not merely an attack test.
_v08_raw_san_parse_san_pattern = parse_san_pattern
_v08_san_guard = False

def _v08_position_outcome(args,kwargs):
    global _v08_san_guard
    if _v08_san_guard: return None
    after=next((kwargs[k] for k in ('after','next_position','candidate','position_after') if k in kwargs and hasattr(kwargs[k],'board')),None)
    if after is None:
        positions=[a for a in args if hasattr(a,'board') and hasattr(a,'turn')]
        after=positions[-1] if len(positions)>=2 else None
    if after is None:return None
    _v08_san_guard=True
    try:
        from . import game_status as gs
        for n in ('analyze_position','analyze_status','classify_position','game_status'):
            fn=getattr(gs,n,None)
            if not callable(fn):continue
            for kw in ({'audit_mode':'none'},{'mode':'none'},{}):
                try:
                    r=fn(after,**kw); d=r if isinstance(r,dict) else r.__dict__
                    return str(d.get('status',d.get('outcome',''))).lower()
                except Exception:pass
    finally:_v08_san_guard=False
    return None

def parse_san_pattern(*args,**kwargs):
    san=_v08_raw_san_parse_san_pattern(*args,**kwargs)
    if not isinstance(san,str):return san
    outcome=_v08_position_outcome(args,kwargs)
    if outcome in ('checkmate','mate','check_mate'):
        return san.rstrip('+#')+'#'
    if outcome in ('check','in_check') and not san.endswith(('+','#')):
        return san+'+'
    return san

