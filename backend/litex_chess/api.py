from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .endgame_training import (
    EndgameTrainer,
    feedback as endgame_feedback,
    lesson as endgame_lesson,
    list_lessons as list_endgame_lessons,
)
from .litex_gate import create_gate
from .model import (
    Move,
    Position,
    PositionFormatError,
    PROMOTION_TO_CODE,
    START_FEN,
    square_to_coords,
)
from .pgn import PGNImportError
from .service import SessionStore
from .textbook import TextbookRuntime
from .version import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORMAL_PATH = Path(
    os.environ.get("LITEX_CHESS_FORMAL", PROJECT_ROOT / "formal" / "chess_rules.lit")
)
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
TEXTBOOK_ROOT = PROJECT_ROOT / "textbook"
TEXTBOOK_SOURCE = TEXTBOOK_ROOT / "chess_rules_textbook_cn.lit"
TEXTBOOK_CATALOG = TEXTBOOK_ROOT / "chapters.json"
CORE_FORMAL_PATH = PROJECT_ROOT / "formal" / "chess_rules.lit"
INTEGRATED_SITE_INDEX = FRONTEND_ROOT / "site" / "index.html"


class NewSessionRequest(BaseModel):
    fen: str = START_FEN
    validate_root: bool = False


class MoveRequest(BaseModel):
    from_square: str = Field(alias="from")
    to_square: str = Field(alias="to")
    promotion: str | None = None
    parent_id: str | None = None


class EndgameMoveRequest(BaseModel):
    from_square: str = Field(alias="from")
    to_square: str = Field(alias="to")
    promotion: str | None = None


class GotoRequest(BaseModel):
    node_id: str


class ImportPGNRequest(BaseModel):
    pgn: str
    validate_root: bool = False


class HeadersRequest(BaseModel):
    headers: dict[str, str]


def _move_from_fields(
    from_square: str,
    to_square: str,
    promotion_text: str | None = None,
) -> Move:
    ff, fr = square_to_coords(from_square.lower())
    tf, tr = square_to_coords(to_square.lower())
    promotion = 0
    if promotion_text:
        key = promotion_text.lower()
        if key not in PROMOTION_TO_CODE:
            raise PositionFormatError("promotion must be q, r, b, or n")
        promotion = PROMOTION_TO_CODE[key]
    return Move(ff, fr, tf, tr, promotion)


def _project_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def create_app() -> FastAPI:
    timeout = float(os.environ.get("LITEX_CHESS_TIMEOUT", "30"))
    include_source = os.environ.get("LITEX_CHESS_INCLUDE_SOURCE", "1") not in {
        "0",
        "false",
        "False",
    }
    gate = create_gate(FORMAL_PATH, timeout=timeout, include_source=include_source)
    store = SessionStore(gate)
    endgames = EndgameTrainer(gate)
    textbook = TextbookRuntime(
        PROJECT_ROOT,
        core_path=CORE_FORMAL_PATH,
        textbook_path=TEXTBOOK_SOURCE,
        catalog_path=TEXTBOOK_CATALOG,
        gate=gate,
        timeout=max(timeout, 45.0),
    )

    app = FastAPI(
        title="Litex Chess Studio",
        version=__version__,
        description=(
            "A fail-closed chess study board whose actual move acceptance is "
            "decided by Litex."
        ),
    )
    app.state.gate = gate
    app.state.store = store
    app.state.textbook = textbook
    app.state.endgames = endgames

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "service": "ok",
            "version": __version__,
            "formal_path": str(FORMAL_PATH),
            "gate": gate.health(),
            "board_transition": "exact sparse delta",
            "agent_record": "move(source,target) + result(status)",
            "policy": "No non-Litex legality fallback. Unknown/error/timeout => reject.",
        }

    @app.get("/api/formal/source")
    def formal_source() -> dict[str, Any]:
        """Return the exact read-only production kernel loaded by the workbench."""

        try:
            source = FORMAL_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"cannot read formal source: {exc}"
            ) from exc
        return {
            "path": str(FORMAL_PATH),
            "project_path": _project_path(FORMAL_PATH),
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "line_count": len(source.splitlines()),
            "source": source,
            "read_only": True,
        }

    # ------------------------------------------------------------------
    # Textbook verification and fixed visual labs
    # ------------------------------------------------------------------
    @app.get("/api/textbook/status")
    def textbook_status() -> dict[str, Any]:
        try:
            return textbook.status()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=500, detail=f"textbook metadata error: {exc}"
            ) from exc

    @app.get("/api/textbook/catalog")
    def textbook_catalog() -> dict[str, Any]:
        """Return the book manifest for Litex-site native navigation."""

        try:
            return json.loads(TEXTBOOK_CATALOG.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail=f"cannot read textbook catalog: {exc}") from exc

    @app.get("/api/textbook/source", response_class=PlainTextResponse)
    def textbook_source() -> str:
        """Return the generated Chinese Litex textbook source."""

        try:
            return TEXTBOOK_SOURCE.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"cannot read textbook source: {exc}") from exc

    @app.post("/api/textbook/verify")
    def verify_textbook() -> dict[str, Any]:
        try:
            return textbook.verify_all(force=True)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise HTTPException(
                status_code=500, detail=f"textbook verification error: {exc}"
            ) from exc

    @app.post("/api/textbook/examples/{example_id}")
    def verify_textbook_example(example_id: str) -> dict[str, Any]:
        try:
            return textbook.verify_example(example_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise HTTPException(
                status_code=500, detail=f"textbook example error: {exc}"
            ) from exc

    @app.get("/api/textbook/board-labs/{lab_id}")
    def get_textbook_board_lab(lab_id: str) -> dict[str, Any]:
        try:
            return textbook.board_lab(lab_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/textbook/board-labs/{lab_id}/moves/{move_id}")
    def verify_textbook_board_move(lab_id: str, move_id: str) -> dict[str, Any]:
        try:
            return textbook.verify_board_move(lab_id, move_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PositionFormatError, ValueError, subprocess.SubprocessError) as exc:
            raise HTTPException(
                status_code=422, detail=f"textbook board lab error: {exc}"
            ) from exc

    @app.post("/api/textbook/status-labs/{lab_id}")
    def verify_textbook_status_lab(lab_id: str) -> dict[str, Any]:
        try:
            return textbook.verify_status_lab(lab_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PositionFormatError, ValueError, subprocess.SubprocessError) as exc:
            raise HTTPException(
                status_code=422, detail=f"textbook status lab error: {exc}"
            ) from exc

    @app.post("/api/textbook/history-labs/{lab_id}")
    def verify_textbook_history_lab(lab_id: str) -> dict[str, Any]:
        try:
            return textbook.verify_history_lab(lab_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PositionFormatError, ValueError, subprocess.SubprocessError) as exc:
            raise HTTPException(
                status_code=422, detail=f"textbook history lab error: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Interactive endgame lessons. Every learner and trainer move goes
    # through Gate.validate_move and therefore the ordinary Litex gate.
    # ------------------------------------------------------------------
    @app.get("/api/textbook/endgames")
    def textbook_endgame_catalog() -> dict[str, Any]:
        return {"lessons": list_endgame_lessons()}

    @app.get("/api/textbook/endgames/feedback/by-fen")
    def textbook_endgame_feedback(fen: str) -> dict[str, Any]:
        try:
            Position.from_fen(fen)
            return endgame_feedback(fen)
        except (PositionFormatError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/textbook/endgames/{lesson_id}/sessions")
    def start_textbook_endgame(lesson_id: str) -> dict[str, Any]:
        try:
            return endgames.start(lesson_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PositionFormatError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/textbook/endgame-sessions/{training_id}")
    def get_textbook_endgame_session(training_id: str) -> dict[str, Any]:
        try:
            return endgames.get(training_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/textbook/endgame-sessions/{training_id}/moves")
    def play_textbook_endgame(
        training_id: str, payload: EndgameMoveRequest
    ) -> dict[str, Any]:
        try:
            move = _move_from_fields(
                payload.from_square, payload.to_square, payload.promotion
            )
            return endgames.play(training_id, move)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PositionFormatError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/textbook/endgame-sessions/{training_id}")
    def delete_textbook_endgame_session(training_id: str) -> dict[str, bool]:
        endgames.delete(training_id)
        return {"deleted": True}

    @app.get("/api/textbook/endgames/{lesson_id}")
    def get_textbook_endgame(lesson_id: str) -> dict[str, Any]:
        try:
            return endgame_lesson(lesson_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # ------------------------------------------------------------------
    # Main chess workbench sessions
    # ------------------------------------------------------------------
    @app.post("/api/sessions")
    def create_session(payload: NewSessionRequest) -> dict[str, Any]:
        try:
            position = Position.from_fen(payload.fen)
            session, root_receipt = store.create(
                position, validate_root=payload.validate_root
            )
        except (PositionFormatError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "session_id": session.id,
            "tree": session.tree.to_dict(),
            "root_receipt": root_receipt,
        }

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        try:
            session = store.get(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"session_id": session.id, "tree": session.tree.to_dict()}

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, bool]:
        store.delete(session_id)
        return {"deleted": True}

    @app.post("/api/sessions/{session_id}/move")
    def play_move(session_id: str, payload: MoveRequest) -> dict[str, Any]:
        try:
            move = _move_from_fields(
                payload.from_square, payload.to_square, payload.promotion
            )
            session = store.get(session_id)
            parent_id = payload.parent_id or session.tree.current_id
            tree, receipt = store.play(session_id, parent_id, move)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (PositionFormatError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "accepted": bool(receipt.get("accepted")),
            "tree": tree,
            "receipt": receipt,
        }

    @app.post("/api/sessions/{session_id}/goto")
    def goto_node(session_id: str, payload: GotoRequest) -> dict[str, Any]:
        try:
            tree = store.goto(session_id, payload.node_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"tree": tree}

    @app.get("/api/sessions/{session_id}/nodes/{node_id}/receipt")
    def get_node_receipt(session_id: str, node_id: str) -> dict[str, Any]:
        try:
            receipt = store.node_receipt(session_id, node_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"node_id": node_id, "receipt": receipt}

    @app.post("/api/import-pgn")
    def import_game(payload: ImportPGNRequest) -> dict[str, Any]:
        try:
            session = store.import_text(
                payload.pgn, validate_root=payload.validate_root
            )
        except PGNImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"session_id": session.id, "tree": session.tree.to_dict()}

    @app.get(
        "/api/sessions/{session_id}/export-pgn", response_class=PlainTextResponse
    )
    def export_game(session_id: str) -> str:
        try:
            session = store.get(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        with session.lock:
            return session.tree.export_pgn()

    @app.put("/api/sessions/{session_id}/headers")
    def update_headers(session_id: str, payload: HeadersRequest) -> dict[str, Any]:
        try:
            session = store.get(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        with session.lock:
            session.tree.headers.update(payload.headers)
            return {"headers": session.tree.headers}

    @app.on_event("shutdown")
    def shutdown() -> None:
        gate.close()

    if TEXTBOOK_ROOT.exists():
        app.mount(
            "/textbook-source",
            StaticFiles(directory=TEXTBOOK_ROOT),
            name="textbook-source",
        )

    if FRONTEND_ROOT.exists():
        # `/extensions/chess` is the production-oriented site-extension path.
        # `/assets` remains only for the standalone compatibility pages.
        app.mount(
            "/extensions/chess",
            StaticFiles(directory=FRONTEND_ROOT),
            name="chess-extension-assets",
        )
        app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT), name="assets")

        def integrated_site() -> FileResponse:
            return FileResponse(INTEGRATED_SITE_INDEX)

        @app.get("/textbook/Chess", include_in_schema=False)
        @app.get("/textbook/Chess/", include_in_schema=False)
        @app.get("/textbook/Chess/{chapter_slug}", include_in_schema=False)
        def chess_textbook_site(chapter_slug: str | None = None) -> FileResponse:
            del chapter_slug
            return integrated_site()

        @app.get("/playground/chess", include_in_schema=False)
        def chess_playground_site() -> FileResponse:
            return integrated_site()

        @app.get("/standalone/workbench", include_in_schema=False)
        def standalone_workbench() -> FileResponse:
            return FileResponse(FRONTEND_ROOT / "index.html")

        @app.get("/standalone/textbook", include_in_schema=False)
        def standalone_textbook() -> FileResponse:
            return FileResponse(FRONTEND_ROOT / "textbook.html")

        @app.get("/textbook", include_in_schema=False)
        def textbook_redirect() -> RedirectResponse:
            return RedirectResponse(url="/textbook/Chess", status_code=307)

        @app.get("/", include_in_schema=False)
        def index() -> RedirectResponse:
            return RedirectResponse(url="/textbook/Chess", status_code=307)

    return app


app = create_app()
