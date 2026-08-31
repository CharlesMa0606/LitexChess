#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import statistics
import time
from pathlib import Path
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from litex_chess.candidate import apply_candidate  # noqa: E402
from litex_chess.litex_gate import SessionLitexGate, SubprocessLitexGate, _LRU  # noqa: E402
from litex_chess.model import Move, Position  # noqa: E402
from litex_chess.query import LitexQueryBuilder  # noqa: E402


def stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    index95 = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return {
        "min_ms": ordered[0],
        "median_ms": statistics.median(ordered),
        "mean_ms": statistics.mean(ordered),
        "p95_ms": ordered[index95],
        "max_ms": ordered[-1],
    }


def measure(fn: Callable[[], object], iterations: int) -> dict[str, float]:
    values: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        fn()
        values.append((time.perf_counter() - started) * 1000)
    return stats(values)


def show(name: str, result: dict[str, float], unit: str = "ms") -> None:
    scale = 1000.0 if unit == "us" else 1.0
    print(
        f"{name:34s} "
        f"median={result['median_ms'] * scale:9.3f} {unit}  "
        f"p95={result['p95_ms'] * scale:9.3f} {unit}  "
        f"min={result['min_ms'] * scale:9.3f} {unit}  "
        f"max={result['max_ms'] * scale:9.3f} {unit}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark python-chess and Litex move gates")
    parser.add_argument("--host-iterations", type=int, default=5000)
    parser.add_argument("--session-iterations", type=int, default=50)
    parser.add_argument("--one-shot-iterations", type=int, default=5)
    parser.add_argument("--python-chess-iterations", type=int, default=100000)
    args = parser.parse_args()

    binary = (
        os.environ.get("LITEX_BIN")
        or os.environ.get("LITEXPY_LITEX_BIN")
        or str(ROOT / "tools" / "litex" / "linux-amd64" / "litex")
    )
    formal = ROOT / "formal" / "chess_rules.lit"
    builder = LitexQueryBuilder.from_file(formal)
    position = Position.initial()
    move = Move.from_uci("e2e4")
    transition = apply_candidate(position, move)
    query = builder.build_move_query(transition)

    print("\nHost-side deterministic certificate compiler")
    show("FEN parse", measure(lambda: Position.from_fen(position.fen), args.host_iterations), "us")
    show("UCI parse", measure(lambda: Move.from_uci("e2e4"), args.host_iterations), "us")
    show("candidate successor", measure(lambda: apply_candidate(position, move), args.host_iterations), "us")
    show("Litex query construction", measure(lambda: builder.build_move_query(transition), max(100, args.host_iterations // 5)), "us")

    print("\nLitex verification")
    session = SessionLitexGate(builder, formal, binary=binary, include_source=False)
    try:
        session_values: list[float] = []
        for _ in range(args.session_iterations):
            session._cache = _LRU(maxsize=1)  # Benchmark verification, not exact-query cache hits.
            receipt = session._execute(query)
            if not receipt.accepted:
                raise RuntimeError(receipt.diagnostics)
            session_values.append(receipt.elapsed_ms)
        show("persistent framed session", stats(session_values))
        print(f"{'session cold boot':34s} {session.health()['boot_ms']:9.3f} ms (paid once)")
    finally:
        session.close()

    if args.one_shot_iterations:
        one_shot = SubprocessLitexGate(builder, binary=binary, include_source=False)
        one_values: list[float] = []
        for _ in range(args.one_shot_iterations):
            one_shot._cache = _LRU(maxsize=1)
            receipt = one_shot._execute(query)
            if not receipt.accepted:
                raise RuntimeError(receipt.diagnostics)
            one_values.append(receipt.elapsed_ms)
        show("one-shot runner", stats(one_values))

    print("\npython-chess (optional)")
    try:
        import chess  # type: ignore
    except ImportError:
        print("python-chess is not installed. Run `pip install chess` to include this section.")
    else:
        board = chess.Board()
        chess_move = chess.Move.from_uci("e2e4")
        show(
            "Board.is_legal(existing objects)",
            measure(lambda: board.is_legal(chess_move), args.python_chess_iterations),
            "us",
        )
        show(
            "list(Board.legal_moves)",
            measure(lambda: list(board.legal_moves), max(1000, args.python_chess_iterations // 10)),
            "us",
        )
        show(
            "FEN + UCI + is_legal",
            measure(
                lambda: chess.Board(position.fen).is_legal(chess.Move.from_uci("e2e4")),
                max(1000, args.python_chess_iterations // 10),
            ),
            "us",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
