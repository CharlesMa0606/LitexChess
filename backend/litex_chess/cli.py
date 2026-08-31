from __future__ import annotations

import argparse
import json
from pathlib import Path

from .litex_gate import create_gate
from .model import Move, Position, START_FEN


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="litex-chess")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    verify = sub.add_parser("verify-move", help="ask Litex to certify one UCI move")
    verify.add_argument("uci")
    verify.add_argument("--fen", default=START_FEN)
    verify.add_argument("--formal", default=str(Path(__file__).resolve().parents[2] / "formal" / "chess_rules.lit"))
    verify.add_argument("--show-source", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "litex_chess.api:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return

    position = Position.from_fen(args.fen)
    move = Move.from_uci(args.uci)
    gate = create_gate(args.formal, include_source=args.show_source)
    try:
        transition, receipt = gate.validate_move(position, move)
        print(json.dumps({
            "transition": transition.to_dict(),
            "receipt": receipt.to_dict(include_source=args.show_source),
        }, ensure_ascii=False, indent=2))
        raise SystemExit(0 if receipt.accepted else 2)
    finally:
        gate.close()


if __name__ == "__main__":
    main()
