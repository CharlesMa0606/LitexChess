from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .endgame_training import LESSONS
from .model import Move, Position, square_to_coords
from .query import LitexQueryBuilder
from .transition_trace import TransitionTraceBuilder
from .game_status import PositionStatusAnalyzer

CHAPTER_MARKER = re.compile(r"^# \[chapter:([a-z0-9-]+):(start|end)\]\s*$")
EXAMPLES_START = "# [chapter:examples:start]"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _code_only(source: str, *, stop_before: str | None = None) -> list[str]:
    """Return meaningful Litex lines with comments and blank lines removed.

    The educational mirror contains one additive examples chapter.  Mirror
    equivalence is therefore checked only before that explicit marker.
    """

    lines: list[str] = []
    for raw in source.splitlines():
        if stop_before is not None and raw.strip() == stop_before:
            break
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(raw.rstrip())
    return lines


def mirror_report(core_path=None, textbook_path=None):
    """Compare the generated textbook mirror with the single runtime kernel.

    Comments and blank lines are pedagogical only.  The executable definition
    stream before the explicit examples marker must match exactly.
    """
    from pathlib import Path
    import hashlib
    root = Path(__file__).resolve().parents[2]
    core = Path(core_path) if core_path is not None else root / "formal" / "chess_rules.lit"
    textbook = Path(textbook_path) if textbook_path is not None else root / "textbook" / "chess_rules_textbook_cn.lit"
    marker = EXAMPLES_START
    core_text = core.read_text(encoding="utf-8")
    textbook_text = textbook.read_text(encoding="utf-8").split(marker, 1)[0]

    def executable_lines(text):
        out=[]
        for raw in text.splitlines():
            stripped=raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.append(raw.rstrip())
        return out

    c=executable_lines(core_text)
    t=executable_lines(textbook_text)
    c_blob=("\n".join(c)+"\n").encode("utf-8")
    t_blob=("\n".join(t)+"\n").encode("utf-8")
    first=None
    for i in range(max(len(c),len(t))):
        a=c[i] if i<len(c) else None
        b=t[i] if i<len(t) else None
        if a!=b:
            first={"index":i+1,"core":a,"textbook":b}
            break
    ok=first is None
    return {
        "in_sync": ok,
        "core_lines": len(c), "textbook_lines": len(t),
        "core_line_count": len(c), "textbook_line_count": len(t),
        "core_sha256": hashlib.sha256(c_blob).hexdigest(),
        "textbook_sha256": hashlib.sha256(t_blob).hexdigest(),
        "first_difference": first,
    }



def parse_chapter_ranges(source: str) -> dict[str, dict[str, int]]:
    opened: dict[str, int] = {}
    ranges: dict[str, dict[str, int]] = {}
    for line_number, raw in enumerate(source.splitlines(), start=1):
        match = CHAPTER_MARKER.match(raw.strip())
        if not match:
            continue
        slug, kind = match.groups()
        if kind == "start":
            if slug in opened or slug in ranges:
                raise ValueError(f"duplicate chapter start marker: {slug}")
            opened[slug] = line_number + 1
        else:
            if slug not in opened:
                raise ValueError(f"chapter end without start: {slug}")
            ranges[slug] = {
                "start_line": opened.pop(slug),
                "end_line": line_number - 1,
            }
    if opened:
        raise ValueError("unclosed chapter markers: " + ", ".join(sorted(opened)))
    return ranges


def load_catalog(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chapters = payload.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("textbook catalog must contain a non-empty chapters list")

    source_modules = payload.get("source_modules")
    if source_modules is not None:
        if not isinstance(source_modules, list) or not source_modules:
            raise ValueError("source_modules must be a non-empty list when provided")
        module_slugs: set[str] = set()
        for module in source_modules:
            slug = module.get("slug") if isinstance(module, dict) else None
            if not isinstance(slug, str) or not slug:
                raise ValueError("every source module needs a slug")
            if slug in module_slugs:
                raise ValueError(f"duplicate source module slug: {slug}")
            module_slugs.add(slug)
    else:
        module_slugs = set()

    chapter_slugs: set[str] = set()
    example_ids: set[str] = set()
    board_lab_ids: set[str] = set()
    status_lab_ids: set[str] = set()
    history_lab_ids: set[str] = set()
    endgame_lab_ids: set[str] = set()
    for chapter in chapters:
        slug = chapter.get("slug")
        if not isinstance(slug, str) or not slug:
            raise ValueError("every textbook chapter needs a slug")
        if slug in chapter_slugs:
            raise ValueError(f"duplicate chapter slug: {slug}")
        chapter_slugs.add(slug)
        refs = chapter.get("source_refs", [slug])
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref for ref in refs):
            raise ValueError(f"chapter {slug} source_refs must be a list of slugs")
        if module_slugs and any(ref not in module_slugs for ref in refs):
            unknown = sorted(ref for ref in refs if ref not in module_slugs)
            raise ValueError(f"chapter {slug} references unknown source modules: {unknown}")
        for example in chapter.get("examples", []):
            example_id = example.get("id")
            if not isinstance(example_id, str) or not example_id:
                raise ValueError(f"chapter {slug} contains an example without an id")
            if example_id in example_ids:
                raise ValueError(f"duplicate textbook example id: {example_id}")
            if not isinstance(example.get("query"), str) or not example["query"].strip():
                raise ValueError(f"example {example_id} has no query")
            if not isinstance(example.get("expected"), bool):
                raise ValueError(f"example {example_id} needs a boolean expected value")
            example_ids.add(example_id)

        for lab in chapter.get("board_labs", []):
            lab_id = lab.get("id")
            if not isinstance(lab_id, str) or not lab_id:
                raise ValueError(f"chapter {slug} contains a board lab without an id")
            if lab_id in board_lab_ids:
                raise ValueError(f"duplicate board lab id: {lab_id}")
            board_lab_ids.add(lab_id)
            fen = lab.get("fen")
            if not isinstance(fen, str) or not fen.strip():
                raise ValueError(f"board lab {lab_id} has no FEN")
            Position.from_fen(fen)
            active_square = lab.get("active_square")
            if active_square is not None:
                if not isinstance(active_square, str):
                    raise ValueError(f"board lab {lab_id} active_square must be a square")
                square_to_coords(active_square.lower())
            moves = lab.get("moves")
            if not isinstance(moves, list) or not moves:
                raise ValueError(f"board lab {lab_id} needs at least one move")
            move_ids: set[str] = set()
            for move_spec in moves:
                move_id = move_spec.get("id")
                if not isinstance(move_id, str) or not move_id:
                    raise ValueError(f"board lab {lab_id} contains a move without an id")
                if move_id in move_ids:
                    raise ValueError(f"duplicate move id {move_id} in board lab {lab_id}")
                move_ids.add(move_id)
                uci = move_spec.get("uci")
                if not isinstance(uci, str) or not uci.strip():
                    raise ValueError(f"board lab {lab_id}/{move_id} has no UCI move")
                move = Move.from_uci(uci)
                if active_square and move.from_square != active_square.lower():
                    raise ValueError(
                        f"board lab {lab_id}/{move_id} must start from locked square {active_square}"
                    )
                if not isinstance(move_spec.get("expected"), bool):
                    raise ValueError(
                        f"board lab {lab_id}/{move_id} needs a boolean expected value"
                    )
            for mark in lab.get("marks", []):
                square = mark.get("square") if isinstance(mark, dict) else None
                if not isinstance(square, str):
                    raise ValueError(f"board lab {lab_id} contains a mark without a square")
                square_to_coords(square.lower())
            for target in lab.get("teaching_targets", []):
                square = target.get("square") if isinstance(target, dict) else None
                if not isinstance(square, str):
                    raise ValueError(f"board lab {lab_id} contains a teaching target without a square")
                square_to_coords(square.lower())
                if target.get("attacker_side", 1) not in (-1, 1):
                    raise ValueError(f"board lab {lab_id} teaching target attacker_side must be ±1")

        endgame_labs = chapter.get("endgame_labs", [])
        if not isinstance(endgame_labs, list):
            raise ValueError(f"chapter {slug} endgame_labs must be a list")
        for lab in endgame_labs:
            lesson_id = lab.get("lesson_id") if isinstance(lab, dict) else None
            if not isinstance(lesson_id, str) or not lesson_id:
                raise ValueError(f"chapter {slug} contains an endgame lab without a lesson_id")
            if lesson_id not in LESSONS:
                raise ValueError(f"chapter {slug} references unknown endgame lesson: {lesson_id}")
            if lesson_id in endgame_lab_ids:
                raise ValueError(f"duplicate endgame lesson reference: {lesson_id}")
            endgame_lab_ids.add(lesson_id)

        for lab in chapter.get("status_labs", []):
            lab_id = lab.get("id")
            if not isinstance(lab_id, str) or not lab_id:
                raise ValueError(f"chapter {slug} contains a status lab without an id")
            if lab_id in status_lab_ids:
                raise ValueError(f"duplicate status lab id: {lab_id}")
            status_lab_ids.add(lab_id)
            fen = lab.get("fen")
            if not isinstance(fen, str) or not fen.strip():
                raise ValueError(f"status lab {lab_id} has no FEN")
            Position.from_fen(fen)
            expected_status = lab.get("expected_status")
            if expected_status not in {"ongoing", "check", "checkmate", "stalemate"}:
                raise ValueError(f"status lab {lab_id} has invalid expected_status")
            for mark in lab.get("marks", []):
                square = mark.get("square") if isinstance(mark, dict) else None
                if not isinstance(square, str):
                    raise ValueError(f"status lab {lab_id} contains a mark without a square")
                square_to_coords(square.lower())

        for lab in chapter.get("history_labs", []):
            lab_id = lab.get("id")
            if not isinstance(lab_id, str) or not lab_id:
                raise ValueError(f"chapter {slug} contains a history lab without an id")
            if lab_id in history_lab_ids:
                raise ValueError(f"duplicate history lab id: {lab_id}")
            history_lab_ids.add(lab_id)
            fen = lab.get("fen")
            if not isinstance(fen, str) or not fen.strip():
                raise ValueError(f"history lab {lab_id} has no FEN")
            Position.from_fen(fen)
            sequence = lab.get("sequence")
            if not isinstance(sequence, list):
                raise ValueError(f"history lab {lab_id} sequence must be a list")
            for uci in sequence:
                if not isinstance(uci, str):
                    raise ValueError(f"history lab {lab_id} contains a non-string move")
                Move.from_uci(uci)

    return payload


def find_litex_binary(project_root: Path, gate: Any | None = None) -> str | None:
    candidates: list[str | None] = [
        getattr(gate, "binary", None),
        os.environ.get("LITEX_BIN"),
        os.environ.get("LITEXPY_LITEX_BIN"),
    ]
    if os.name == "nt":
        candidates.extend(
            [
                str(project_root / "tools" / "litex" / "windows-amd64" / "litex.exe"),
                str(project_root / ".local" / "bin" / "litex.exe"),
            ]
        )
    else:
        candidates.extend(
            [
                str(project_root / "tools" / "litex" / "linux-amd64" / "litex"),
                str(project_root / ".local" / "bin" / "litex"),
            ]
        )
    candidates.append(shutil.which("litex"))

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        if os.name != "nt" and not os.access(path, os.X_OK):
            try:
                path.chmod(path.stat().st_mode | 0o111)
            except OSError:
                continue
        if os.name == "nt" or os.access(path, os.X_OK):
            return str(path.resolve())
    return None


def _json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    index = 0
    while index < len(text):
        if text[index] != "{":
            index += 1
            continue
        try:
            value, offset = decoder.raw_decode(text[index:])
        except ValueError:
            index += 1
            continue
        if isinstance(value, dict):
            objects.append(value)
        index += max(offset, 1)
    return objects


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: event[key]
        for key in ("result", "type", "line", "statement", "message", "error")
        if key in event
    }


@dataclass(frozen=True)
class LitexRun:
    accepted: bool
    returncode: int
    elapsed_ms: float
    statement_count: int
    success_count: int
    diagnostics: list[str]
    events: list[dict[str, Any]]
    output_tail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "returncode": self.returncode,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "statement_count": self.statement_count,
            "success_count": self.success_count,
            "diagnostics": self.diagnostics,
            "events": self.events,
            "output_tail": self.output_tail,
        }


def run_litex_source(
    binary: str,
    source: str,
    *,
    timeout: float = 45.0,
) -> LitexRun:
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="litex-chess-textbook-") as tmp:
        root = Path(tmp)
        entry = root / "entry.lit"
        entry.write_text(source, encoding="utf-8")
        process = subprocess.run(
            [binary, "-compact", "-runner", "-isolated", "-f", str(entry)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000

    wrappers = _json_objects(process.stdout)
    wrapper = wrappers[-1] if wrappers else {}
    trace = wrapper.get("trace", "") if isinstance(wrapper, dict) else ""
    events = _json_objects(trace) if isinstance(trace, str) else []
    failures = [event for event in events if event.get("result") != "success"]
    diagnostics: list[str] = []
    for event in failures:
        for key in ("message", "error", "statement"):
            value = event.get(key)
            if value:
                diagnostics.append(str(value))
                break
        if len(diagnostics) >= 6:
            break
    if not diagnostics and process.returncode != 0:
        diagnostics.append(
            str(wrapper.get("error"))
            if isinstance(wrapper, dict) and wrapper.get("error")
            else process.stdout[-2000:]
        )

    accepted = bool(
        process.returncode == 0
        and isinstance(wrapper, dict)
        and wrapper.get("ok") is True
        and events
        and not failures
    )
    compact_events = [_compact_event(event) for event in events[-12:]]
    return LitexRun(
        accepted=accepted,
        returncode=process.returncode,
        elapsed_ms=elapsed_ms,
        statement_count=len(events),
        success_count=sum(event.get("result") == "success" for event in events),
        diagnostics=diagnostics,
        events=compact_events,
        output_tail=process.stdout[-4000:],
    )


class TextbookRuntime:
    """Read-only catalog plus whitelisted Litex teaching executions."""

    def __init__(
        self,
        project_root: Path,
        core_path: Path,
        textbook_path: Path,
        catalog_path: Path,
        gate: Any | None = None,
        timeout: float = 45.0,
    ) -> None:
        self.project_root = project_root
        self.core_path = core_path
        self.textbook_path = textbook_path
        self.catalog_path = catalog_path
        self.gate = gate
        self.timeout = timeout
        self.query_builder = LitexQueryBuilder.from_file(core_path)
        self.trace_builder = TransitionTraceBuilder(self.query_builder)
        self.status_analyzer = (
            PositionStatusAnalyzer(gate, self.query_builder)
            if gate is not None
            else None
        )
        self._lock = threading.RLock()
        self._verify_cache: tuple[str, dict[str, Any]] | None = None

    def _source(self) -> str:
        return self.textbook_path.read_text(encoding="utf-8")

    def _catalog(self) -> dict[str, Any]:
        return load_catalog(self.catalog_path)

    def _examples(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for chapter in self._catalog()["chapters"]:
            for example in chapter.get("examples", []):
                result[example["id"]] = {
                    **example,
                    "chapter": chapter["slug"],
                    "chapter_number": chapter["number"],
                }
        return result

    def _board_labs(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for chapter in self._catalog()["chapters"]:
            for lab in chapter.get("board_labs", []):
                moves = {move["id"]: move for move in lab.get("moves", [])}
                result[lab["id"]] = {
                    **lab,
                    "moves_by_id": moves,
                    "chapter": chapter["slug"],
                    "chapter_number": chapter["number"],
                }
        return result

    def _status_labs(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for chapter in self._catalog()["chapters"]:
            for lab in chapter.get("status_labs", []):
                result[lab["id"]] = {
                    **lab,
                    "chapter": chapter["slug"],
                    "chapter_number": chapter["number"],
                }
        return result

    def _history_labs(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for chapter in self._catalog()["chapters"]:
            for lab in chapter.get("history_labs", []):
                result[lab["id"]] = {
                    **lab,
                    "chapter": chapter["slug"],
                    "chapter_number": chapter["number"],
                }
        return result

    def _endgame_labs(self) -> dict[str, dict[str, Any]]:
        """Return the unique endgame lessons referenced by the curriculum.

        Chapters may reference a lesson through a narrative method list, the
        interactive trainer list, or an explicit ``endgame_labs`` object.  The
        runtime catalogue remains the single source for the actual FEN and
        training contract.
        """

        result: dict[str, dict[str, Any]] = {}
        for chapter in self._catalog()["chapters"]:
            explicit = {lab["lesson_id"]: lab for lab in chapter.get("endgame_labs", [])}
            lesson_ids = [
                *chapter.get("endgame_courses", []),
                *chapter.get("interactive_endgames", []),
                *explicit,
            ]
            for lesson_id in lesson_ids:
                if lesson_id not in LESSONS:
                    raise ValueError(f"unknown endgame lesson in catalog: {lesson_id}")
                payload = {
                    **LESSONS[lesson_id].json(),
                    **explicit.get(lesson_id, {}),
                    "chapter": chapter["slug"],
                    "chapter_number": chapter["number"],
                }
                result[lesson_id] = payload
        return result

    def board_lab(self, lab_id: str) -> dict[str, Any]:
        """Return one whitelisted board lab for workbench deep linking."""
        try:
            lab = self._board_labs()[lab_id]
        except KeyError as exc:
            raise KeyError(f"unknown textbook board lab: {lab_id}") from exc
        public = {key: value for key, value in lab.items() if key != "moves_by_id"}
        public["workbench_url"] = f"/textbook/Chess/workbench?lab={lab_id}&return=/textbook/Chess/{public['chapter']}"
        public["textbook_url"] = f"/textbook/Chess/{public['chapter']}"
        return public

    def status(self) -> dict[str, Any]:
        source = self._source()
        catalog = self._catalog()
        ranges = parse_chapter_ranges(source)
        catalog_slugs = [chapter["slug"] for chapter in catalog["chapters"]]
        module_slugs = [
            module["slug"]
            for module in catalog.get(
                "source_modules",
                [{"slug": slug} for slug in catalog_slugs],
            )
        ]
        marker_slugs = list(ranges)
        binary = find_litex_binary(self.project_root, self.gate)
        examples = self._examples()
        board_labs = self._board_labs()
        status_labs = self._status_labs()
        history_labs = self._history_labs()
        endgame_labs = self._endgame_labs()
        board_moves = sum(len(lab["moves_by_id"]) for lab in board_labs.values())
        gate_health = self.gate.health() if self.gate is not None else {"ready": False}
        return {
            "ready": binary is not None,
            "interactive_ready": bool(self.gate is not None and gate_health.get("ready")),
            "binary": binary,
            "source": str(self.textbook_path.relative_to(self.project_root)),
            "core_source": str(self.core_path.relative_to(self.project_root)),
            "catalog": str(self.catalog_path.relative_to(self.project_root)),
            "source_sha256": _sha256_text(source),
            "chapter_count": len(catalog_slugs),
            "example_count": len(examples),
            "board_lab_count": len(board_labs),
            "board_move_count": board_moves,
            "status_lab_count": len(status_labs),
            "history_lab_count": len(history_labs),
            "endgame_lab_count": len(endgame_labs),
            "chapter_ranges": ranges,
            "source_module_count": len(module_slugs),
            "markers_match_catalog": module_slugs == marker_slugs,
            "mirror": mirror_report(self.core_path, self.textbook_path),
            "policy": (
                "The runtime rule engine loads formal/chess_rules.lit only. "
                "Textbook runs use a fixed local source and whitelisted examples."
            ),
        }

    def verify_all(self, *, force: bool = False) -> dict[str, Any]:
        source = self._source()
        source_hash = _sha256_text(source)
        with self._lock:
            if not force and self._verify_cache and self._verify_cache[0] == source_hash:
                return {**self._verify_cache[1], "cached": True}
            binary = find_litex_binary(self.project_root, self.gate)
            if binary is None:
                return {
                    "ok": False,
                    "cached": False,
                    "reason": "Litex executable not found",
                    "mirror": mirror_report(self.core_path, self.textbook_path),
                }
            run = run_litex_source(binary, source, timeout=self.timeout)
            mirror = mirror_report(self.core_path, self.textbook_path)
            payload = {
                "ok": bool(run.accepted and mirror["in_sync"]),
                "cached": False,
                "binary": binary,
                "mirror": mirror,
                "run": run.to_dict(),
                "reason": (
                    "教材全部语句已由 Litex 接受，且生产定义镜像与运行时内核逐行同步。"
                    if run.accepted and mirror["in_sync"]
                    else "教材编译或核心镜像同步检查未通过。"
                ),
            }
            self._verify_cache = (source_hash, payload)
            return payload

    def verify_example(self, example_id: str) -> dict[str, Any]:
        examples = self._examples()
        try:
            example = examples[example_id]
        except KeyError as exc:
            raise KeyError(f"unknown textbook example: {example_id}") from exc
        binary = find_litex_binary(self.project_root, self.gate)
        if binary is None:
            return {
                "ok": False,
                "example_id": example_id,
                "reason": "Litex executable not found",
            }

        base = self._source().rstrip() + "\n\n"
        query = example["query"].strip()
        source = (
            base
            + f"# 网页教材白名单示例：{example_id}\n"
            + query
            + "\n"
        )
        run = run_litex_source(binary, source, timeout=self.timeout)
        observed = run.accepted
        expected = bool(example["expected"])
        return {
            "ok": observed == expected,
            "example_id": example_id,
            "chapter": example["chapter"],
            "title": example.get("title", example_id),
            "query": query,
            "expected": expected,
            "observed": observed,
            "classification": "accepted" if observed else "rejected",
            "reason": (
                "Litex 的实际判定与教材预期一致。"
                if observed == expected
                else "Litex 的实际判定与教材预期不一致。"
            ),
            "run": run.to_dict(),
        }

    def verify_board_move(self, lab_id: str, move_id: str) -> dict[str, Any]:
        labs = self._board_labs()
        try:
            lab = labs[lab_id]
        except KeyError as exc:
            raise KeyError(f"unknown textbook board lab: {lab_id}") from exc
        try:
            move_spec = lab["moves_by_id"][move_id]
        except KeyError as exc:
            raise KeyError(f"unknown move {move_id} in textbook board lab {lab_id}") from exc
        if self.gate is None:
            return {
                "ok": False,
                "lab_id": lab_id,
                "move_id": move_id,
                "reason": "Interactive Litex move gate is not available",
            }

        position = Position.from_fen(lab["fen"])
        move = Move.from_uci(move_spec["uci"])
        active_square = lab.get("active_square")
        if active_square and move.from_square != active_square.lower():
            raise ValueError(
                f"board lab {lab_id} locks input to {active_square}; got {move.from_square}"
            )
        transition, receipt = self.gate.validate_move(position, move)
        observed = bool(receipt.accepted)
        expected = bool(move_spec["expected"])
        trace = self.trace_builder.build(
            transition,
            teaching_targets=lab.get("teaching_targets", []),
        )
        trace["pipeline"][-1]["outcome"] = (
            "Litex 接受，候选 after 可以提交为新棋谱节点。"
            if observed
            else "Litex 拒绝，候选 after 仅供解释，棋谱中的当前局面保持不变。"
        )
        return {
            "ok": observed == expected,
            "lab_id": lab_id,
            "move_id": move_id,
            "chapter": lab["chapter"],
            "title": lab.get("title", lab_id),
            "move": move_spec,
            "expected": expected,
            "observed": observed,
            "classification": "accepted" if observed else "rejected",
            "reason": (
                "完整落子门禁的实际判定与教材预期一致。"
                if observed == expected
                else "完整落子门禁的实际判定与教材预期不一致。"
            ),
            "before": position.to_dict(),
            "candidate_after": transition.after.to_dict(),
            "committed_after": (transition.after if observed else position).to_dict(),
            "transition": transition.to_dict(),
            "trace": trace,
            "receipt": receipt.to_dict(include_source=True),
        }

    def verify_status_lab(self, lab_id: str) -> dict[str, Any]:
        labs = self._status_labs()
        try:
            lab = labs[lab_id]
        except KeyError as exc:
            raise KeyError(f"unknown textbook status lab: {lab_id}") from exc
        if self.status_analyzer is None:
            return {"ok": False, "lab_id": lab_id, "reason": "Interactive Litex move gate is not available"}
        position = Position.from_fen(lab["fen"])
        analysis = self.status_analyzer.analyze(position)
        expected = lab["expected_status"]
        status_ok = analysis["status"] == expected
        expected_dead = lab.get("expected_dead_position")
        dead_ok = (
            True
            if expected_dead is None
            else bool(analysis.get("dead_position", {}).get("dead")) is bool(expected_dead)
        )
        ok = bool(status_ok and dead_ok)
        return {
            "ok": ok,
            "lab_id": lab_id,
            "chapter": lab["chapter"],
            "title": lab.get("title", lab_id),
            "expected_status": expected,
            "observed_status": analysis["status"],
            "expected_dead_position": expected_dead,
            "observed_dead_position": bool(analysis.get("dead_position", {}).get("dead")),
            "analysis": analysis,
            "reason": (
                "合法着集合与死局分类均与教材预期一致。"
                if ok
                else "局面状态或死局分类与教材预期不一致。"
            ),
        }

    def verify_history_lab(self, lab_id: str) -> dict[str, Any]:
        labs = self._history_labs()
        try:
            lab = labs[lab_id]
        except KeyError as exc:
            raise KeyError(f"unknown textbook history lab: {lab_id}") from exc
        if self.status_analyzer is None:
            return {"ok": False, "lab_id": lab_id, "reason": "Interactive Litex move gate is not available"}
        position = Position.from_fen(lab["fen"])
        result = self.status_analyzer.run_history(position, list(lab.get("sequence", [])))
        expected = lab.get("expect", {})
        final = result["final"]
        checks = {
            key: final.get(key) == value
            for key, value in expected.items()
        }
        ok = bool(result["accepted"] and all(checks.values()))
        return {
            "ok": ok,
            "lab_id": lab_id,
            "chapter": lab["chapter"],
            "title": lab.get("title", lab_id),
            "expected": expected,
            "checks": checks,
            "result": result,
            "reason": "历史状态实验与教材预期一致。" if ok else "历史状态实验与教材预期不一致。",
        }

