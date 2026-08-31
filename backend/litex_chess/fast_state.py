"""Exact pseudo-legal generation and terminal-state classification.

This module is intentionally independent from the Litex move gate.  It
supplies a finite exact candidate set for checkmate/stalemate scans and
SAN suffixes.  A user move is never accepted merely because this module
generated it; the normal Litex certificate remains mandatory.
"""
from __future__ import annotations
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Iterator

FILES = "abcdefgh"
PROMOS = "qrbn"
KNIGHT = ((1,2),(2,1),(2,-1),(1,-2),(-1,-2),(-2,-1),(-2,1),(-1,2))
KING = ((1,0),(1,1),(0,1),(-1,1),(-1,0),(-1,-1),(0,-1),(1,-1))
BISHOP = ((1,1),(1,-1),(-1,1),(-1,-1))
ROOK = ((1,0),(-1,0),(0,1),(0,-1))

@dataclass(frozen=True, slots=True)
class Move:
    source: int
    target: int
    promotion: str = ""

    @property
    def uci(self) -> str:
        return square_name(self.source) + square_name(self.target) + self.promotion

def square_name(index: int) -> str:
    return FILES[index % 8] + str(index // 8 + 1)

def parse_square(name: str) -> int:
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])

def color(piece: str) -> str | None:
    if not piece: return None
    return "w" if piece.isupper() else "b"

def enemy(side: str) -> str:
    return "b" if side == "w" else "w"

@dataclass(frozen=True, slots=True)
class FastPosition:
    board: tuple[str, ...]
    turn: str
    castling: str
    ep: int | None
    halfmove: int
    fullmove: int

    @classmethod
    def from_fen(cls, fen: str) -> "FastPosition":
        placement, turn, castling, ep, half, full = fen.split()
        board = [""] * 64
        ranks = placement.split("/")
        if len(ranks) != 8: raise ValueError("invalid FEN")
        for fr, token in enumerate(ranks):
            rank = 7 - fr; file_ = 0
            for ch in token:
                if ch.isdigit(): file_ += int(ch)
                else:
                    board[rank*8+file_] = ch; file_ += 1
            if file_ != 8: raise ValueError("invalid FEN rank")
        return cls(tuple(board), turn, "" if castling == "-" else castling,
                   None if ep == "-" else parse_square(ep), int(half), int(full))

    def fen(self) -> str:
        ranks = []
        for rank in range(7,-1,-1):
            token=""; empty=0
            for file_ in range(8):
                p=self.board[rank*8+file_]
                if p: 
                    if empty: token += str(empty); empty=0
                    token += p
                else: empty += 1
            if empty: token += str(empty)
            ranks.append(token)
        return f"{'/'.join(ranks)} {self.turn} {self.castling or '-'} {square_name(self.ep) if self.ep is not None else '-'} {self.halfmove} {self.fullmove}"

    def king_square(self, side: str) -> int:
        king = "K" if side == "w" else "k"
        try: return self.board.index(king)
        except ValueError: return -1

    def attacked(self, sq: int, by: str) -> bool:
        b=self.board; f=sq%8; r=sq//8
        # Pawn sources that attack sq.
        dr = -1 if by == "w" else 1
        pawn = "P" if by == "w" else "p"
        for df in (-1,1):
            sf=f+df; sr=r+dr
            if 0<=sf<8 and 0<=sr<8 and b[sr*8+sf]==pawn: return True
        knight = "N" if by=="w" else "n"
        for df,dr2 in KNIGHT:
            sf=f+df; sr=r+dr2
            if 0<=sf<8 and 0<=sr<8 and b[sr*8+sf]==knight: return True
        king = "K" if by=="w" else "k"
        for df,dr2 in KING:
            sf=f+df; sr=r+dr2
            if 0<=sf<8 and 0<=sr<8 and b[sr*8+sf]==king: return True
        for dirs, pieces in ((BISHOP, ("B","Q") if by=="w" else ("b","q")),
                             (ROOK, ("R","Q") if by=="w" else ("r","q"))):
            for df,dr2 in dirs:
                sf=f+df; sr=r+dr2
                while 0<=sf<8 and 0<=sr<8:
                    p=b[sr*8+sf]
                    if p:
                        if p in pieces: return True
                        break
                    sf+=df; sr+=dr2
        return False

    def in_check(self, side: str | None = None) -> bool:
        s=side or self.turn; k=self.king_square(s)
        return k >= 0 and self.attacked(k, enemy(s))

    def pseudo_legal(self) -> tuple[Move, ...]:
        out=[]; side=self.turn; b=self.board
        for src,p in enumerate(b):
            if color(p)!=side: continue
            f=src%8; r=src//8; kind=p.lower()
            if kind=="p":
                step=1 if side=="w" else -1; start=1 if side=="w" else 6; promo=7 if side=="w" else 0
                tr=r+step
                if 0<=tr<8:
                    dst=tr*8+f
                    if not b[dst]:
                        if tr==promo:
                            out.extend(Move(src,dst,x) for x in PROMOS)
                        else:
                            out.append(Move(src,dst))
                            if r==start:
                                dst2=(r+2*step)*8+f
                                if not b[dst2]: out.append(Move(src,dst2))
                    for df in (-1,1):
                        tf=f+df
                        if 0<=tf<8:
                            d=tr*8+tf; target=b[d]
                            capturable = target and color(target) == enemy(side) and target.lower() != "k"
                            if capturable or d == self.ep:
                                if tr == promo:
                                    out.extend(Move(src, d, x) for x in PROMOS)
                                else:
                                    out.append(Move(src, d))
            elif kind=="n":
                for df,dr in KNIGHT:
                    tf=f+df; tr=r+dr
                    if 0<=tf<8 and 0<=tr<8:
                        d=tr*8+tf
                        if color(b[d]) != side and b[d].lower() != "k":
                            out.append(Move(src, d))
            elif kind in {"b","r","q"}:
                dirs = BISHOP if kind=="b" else ROOK if kind=="r" else BISHOP+ROOK
                for df,dr in dirs:
                    tf=f+df; tr=r+dr
                    while 0<=tf<8 and 0<=tr<8:
                        d=tr*8+tf
                        if not b[d]: out.append(Move(src,d))
                        else:
                            if color(b[d]) != side and b[d].lower() != "k":
                                out.append(Move(src, d))
                            break
                        tf+=df; tr+=dr
            elif kind=="k":
                for df,dr in KING:
                    tf=f+df; tr=r+dr
                    if 0<=tf<8 and 0<=tr<8:
                        d=tr*8+tf
                        if color(b[d]) != side and b[d].lower() != "k":
                            out.append(Move(src, d))
                if side=="w" and src==4:
                    if "K" in self.castling and not b[5] and not b[6] and b[7]=="R" and not self.in_check("w") and not self.attacked(5,"b") and not self.attacked(6,"b"):
                        out.append(Move(4,6))
                    if "Q" in self.castling and not b[1] and not b[2] and not b[3] and b[0]=="R" and not self.in_check("w") and not self.attacked(3,"b") and not self.attacked(2,"b"):
                        out.append(Move(4,2))
                if side=="b" and src==60:
                    if "k" in self.castling and not b[61] and not b[62] and b[63]=="r" and not self.in_check("b") and not self.attacked(61,"w") and not self.attacked(62,"w"):
                        out.append(Move(60,62))
                    if "q" in self.castling and not b[57] and not b[58] and not b[59] and b[56]=="r" and not self.in_check("b") and not self.attacked(59,"w") and not self.attacked(58,"w"):
                        out.append(Move(60,58))
        return tuple(out)

    def apply(self, move: Move) -> "FastPosition":
        b = list(self.board)
        moving = b[move.source]
        target = b[move.target]
        side = self.turn
        if not moving or color(moving) != side:
            raise ValueError("move source does not contain a side-to-move piece")
        if target.lower() == "k":
            raise ValueError("the king is checked, never captured")

        sf, sr = move.source % 8, move.source // 8
        tf, tr = move.target % 8, move.target // 8
        b[move.source] = ""
        captured_piece = target

        # En passant removes the pawn behind the empty target square.
        if moving.lower() == "p" and move.target == self.ep and not target and sf != tf:
            captured = move.target + (-8 if side == "w" else 8)
            captured_piece = b[captured]
            b[captured] = ""

        # Castling moves the rook as part of the same local transition.
        if moving == "K" and move.source == 4 and move.target in (2, 6):
            rook_source, rook_target = ((0, 3) if move.target == 2 else (7, 5))
            b[rook_target] = b[rook_source]
            b[rook_source] = ""
        elif moving == "k" and move.source == 60 and move.target in (58, 62):
            rook_source, rook_target = ((56, 59) if move.target == 58 else (63, 61))
            b[rook_target] = b[rook_source]
            b[rook_source] = ""

        placed = moving
        if move.promotion:
            if moving.lower() != "p" or tr not in (0, 7):
                raise ValueError("promotion is only available to a pawn on the last rank")
            placed = move.promotion.upper() if side == "w" else move.promotion.lower()
        b[move.target] = placed

        rights = self.castling
        if moving == "K":
            rights = rights.replace("K", "").replace("Q", "")
        elif moving == "k":
            rights = rights.replace("k", "").replace("q", "")
        for square, flag in ((0, "Q"), (7, "K"), (56, "q"), (63, "k")):
            if move.source == square or move.target == square:
                rights = rights.replace(flag, "")

        ep = None
        if moving.lower() == "p" and abs(tr - sr) == 2:
            ep = (move.source + move.target) // 2
        halfmove = 0 if moving.lower() == "p" or captured_piece else self.halfmove + 1
        fullmove = self.fullmove + int(side == "b")
        return FastPosition(tuple(b), enemy(side), rights, ep, halfmove, fullmove)

    def legal_moves(self) -> tuple[Move, ...]:
        side=self.turn; out=[]
        for m in self.pseudo_legal():
            try: child=self.apply(m)
            except Exception: continue
            if not child.in_check(side): out.append(m)
        return tuple(out)

    def status(self, legal: tuple[Move, ...] | None = None) -> str:
        moves = self.legal_moves() if legal is None else legal
        checked = self.in_check()
        if moves:
            return "check" if checked else "ongoing"
        return "checkmate" if checked else "stalemate"

@lru_cache(maxsize=8192)
def analyze_fen(fen: str) -> dict[str, object]:
    p = FastPosition.from_fen(fen)
    pseudo = p.pseudo_legal()
    legal = p.legal_moves()
    checked = p.in_check()
    status = p.status(legal)
    return {
        "status": status,
        "in_check": checked,
        "legal_count": len(legal),
        "legal_uci": [m.uci for m in legal],
        "pseudo_legal_count": len(pseudo),
    }

def perft(fen: str, depth: int) -> int:
    p=FastPosition.from_fen(fen)
    def rec(pos: FastPosition, d: int) -> int:
        if d==0: return 1
        return sum(rec(pos.apply(m),d-1) for m in pos.legal_moves())
    return rec(p,depth)
