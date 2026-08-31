from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .model import GateReceipt, Move, Position


@dataclass(slots=True)
class GameNode:
    id: str
    parent_id: str | None
    position: Position
    move: Move | None = None
    san: str | None = None
    children: list[str] = field(default_factory=list)
    comment: str = ""
    nags: list[str] = field(default_factory=list)
    receipt: GateReceipt | None = None

    def to_dict(self, include_receipt: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "parent_id": self.parent_id,
            "position": self.position.to_dict(),
            "move": None if self.move is None else self.move.to_dict(),
            "san": self.san,
            "children": list(self.children),
            "comment": self.comment,
            "nags": list(self.nags),
        }
        if include_receipt:
            payload["receipt"] = None if self.receipt is None else self.receipt.to_dict()
        return payload


class GameTree:
    def __init__(self, root_position: Position, headers: dict[str, str] | None = None) -> None:
        root_id = "root"
        self.nodes: dict[str, GameNode] = {
            root_id: GameNode(root_id, None, root_position)
        }
        self.root_id = root_id
        self.current_id = root_id
        self.headers = {
            "Event": "Litex Chess Study",
            "Site": "Local",
            "Date": "????.??.??",
            "Round": "-",
            "White": "White",
            "Black": "Black",
            "Result": "*",
        }
        if headers:
            self.headers.update(headers)

    @property
    def current(self) -> GameNode:
        return self.nodes[self.current_id]

    def goto(self, node_id: str) -> GameNode:
        if node_id not in self.nodes:
            raise KeyError(f"unknown node id: {node_id}")
        self.current_id = node_id
        return self.current

    def add_move(
        self,
        parent_id: str,
        move: Move,
        san: str,
        position: Position,
        receipt: GateReceipt,
    ) -> GameNode:
        if parent_id not in self.nodes:
            raise KeyError(f"unknown parent node: {parent_id}")
        parent = self.nodes[parent_id]
        for child_id in parent.children:
            child = self.nodes[child_id]
            if child.move and child.move.uci == move.uci:
                self.current_id = child.id
                return child
        node_id = uuid.uuid4().hex[:16]
        node = GameNode(
            id=node_id,
            parent_id=parent_id,
            position=position,
            move=move,
            san=san,
            receipt=receipt,
        )
        self.nodes[node_id] = node
        parent.children.append(node_id)
        self.current_id = node_id
        return node

    def ancestors(self, node_id: str | None = None) -> list[GameNode]:
        cursor = self.nodes[node_id or self.current_id]
        result: list[GameNode] = []
        while cursor.parent_id is not None:
            result.append(cursor)
            cursor = self.nodes[cursor.parent_id]
        result.reverse()
        return result

    def to_dict(self, include_receipts: bool = False) -> dict[str, Any]:
        return {
            "root_id": self.root_id,
            "current_id": self.current_id,
            "headers": dict(self.headers),
            "nodes": {
                node_id: node.to_dict(include_receipt=include_receipts)
                for node_id, node in self.nodes.items()
            },
            "path": [node.to_dict(include_receipt=False) for node in self.ancestors()],
        }

    def _move_prefix(self, parent: GameNode, variation_start: bool) -> str:
        pos = parent.position
        if pos.turn == 1:
            return f"{pos.fullmove}."
        return f"{pos.fullmove}..." if variation_start else ""

    def _emit_line(
        self,
        parent_id: str,
        first_child_id: str | None = None,
        variation_start: bool = False,
        include_siblings: bool = True,
    ) -> list[str]:
        parent = self.nodes[parent_id]
        if not parent.children:
            return []
        child_id = first_child_id or parent.children[0]
        child = self.nodes[child_id]
        tokens: list[str] = []
        prefix = self._move_prefix(parent, variation_start)
        if prefix:
            tokens.append(prefix)
        tokens.append(child.san or (child.move.uci if child.move else ""))
        if child.comment:
            tokens.append("{" + child.comment.replace("}", "") + "}")
        tokens.extend(child.nags)

        # An alternate branch must not recursively re-emit the same sibling set;
        # descendant positions may still carry their own variations.
        if include_siblings:
            for alternate_id in parent.children:
                if alternate_id == child_id:
                    continue
                alt_tokens = self._emit_line(
                    parent_id,
                    alternate_id,
                    variation_start=True,
                    include_siblings=False,
                )
                tokens.extend(["(", *alt_tokens, ")"])
        tokens.extend(
            self._emit_line(
                child_id,
                variation_start=False,
                include_siblings=True,
            )
        )
        return tokens

    def export_pgn(self) -> str:
        headers = dict(self.headers)
        root = self.nodes[self.root_id]
        from .model import START_FEN

        if root.position.fen != START_FEN:
            headers["SetUp"] = "1"
            headers["FEN"] = root.position.fen
        header_text = "\n".join(
            f'[{key} "{value.replace(chr(34), chr(39))}"]'
            for key, value in headers.items()
        )
        tokens = self._emit_line(self.root_id, variation_start=True)
        result = headers.get("Result", "*")
        if not tokens or tokens[-1] not in {"1-0", "0-1", "1/2-1/2", "*"}:
            tokens.append(result)
        # Keep parentheses tight enough for ordinary PGN readers while remaining readable.
        movetext = " ".join(token for token in tokens if token)
        movetext = movetext.replace("( ", "(").replace(" )", ")")
        return header_text + "\n\n" + movetext.strip() + "\n"
