from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FORMAL = ROOT / "formal"
RESEARCH = ROOT / "research" / "formal"


def _without_comments_and_strings(source: str) -> str:
    source = re.sub(r'""".*?"""', "", source, flags=re.S)
    return re.sub(r"#.*", "", source)


def test_runtime_and_research_formal_sources_contain_no_trust_or_axiom_statement():
    files = [FORMAL / "chess_rules.lit", *sorted(RESEARCH.glob("*.lit"))]
    assert all(path.is_file() for path in files)
    assert {path.name for path in files} >= {
        "chess_rules.lit",
        "certificate_contract.lit",
        "chess_specification_full.lit",
    }
    for path in files:
        stripped = _without_comments_and_strings(path.read_text(encoding="utf-8"))
        assert not re.search(r"\btrust\b", stripped), path
        assert not re.search(r"\baxiom\b", stripped), path


def test_runtime_kernel_covers_special_moves_sparse_board_metadata_and_safety():
    source = (FORMAL / "chess_rules.lit").read_text(encoding="utf-8")
    for name in (
        "move",
        "result",
        "result_witness",
        "en_passant_move",
        "pawn_promotion",
        "white_kingside_castle",
        "black_queenside_castle",
        "sparse_square_edit",
        "sparse_board_transition",
        "king_safe",
        "metadata_transition",
        "legal_transition",
    ):
        assert f"prop {name}" in source
    assert "prop board_rank_transition" not in source


def test_relational_blueprint_is_separate_and_marks_extension_points_explicitly():
    source = (RESEARCH / "chess_specification_full.lit").read_text(encoding="utf-8")
    assert "abstract_prop board_total" in source
    assert "prop legal_edge" in source
    assert not (FORMAL / "chess_specification_full.lit").exists()
    assert not (FORMAL / "certificate_contract.lit").exists()
