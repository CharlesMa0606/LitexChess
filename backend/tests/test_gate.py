from litex_chess.litex_gate import UnavailableGate, results_successful
from litex_chess.model import Move, Position


def test_nested_success_parser():
    results = [{"result": "success", "inside_results": [{"result": "success"}]}]
    assert results_successful(results)


def test_nested_error_parser():
    results = [{"result": "success", "inside_results": [{"result": "error"}]}]
    assert not results_successful(results)


def test_missing_litex_fails_closed_and_never_accepts():
    gate = UnavailableGate(["binary missing"])
    _, receipt = gate.validate_move(Position.initial(), Move.from_uci("e2e4"))
    assert not receipt.accepted
    assert "never falls back" in receipt.reason
