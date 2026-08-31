from litex_chess.pgn import import_pgn, parse_san_pattern
from litex_chess.model import Position


def test_san_pattern_for_pawn_and_castle():
    position = Position.initial()
    e4 = parse_san_pattern("e4", position)
    assert e4.piece_kind == 1 and e4.to_file == 5 and e4.to_rank == 4
    castle = parse_san_pattern("O-O", position)
    assert castle.castle == "O-O" and castle.to_file == 7


def test_pgn_mainline_and_black_variation_are_retained(scripted_gate):
    pgn = '''[Event "Variation test"]
[Result "*"]

1. e4 e5 (1... c5) 2. Nf3 Nc6 *
'''
    tree = import_pgn(scripted_gate, pgn, validate_root=True)
    root = tree.nodes[tree.root_id]
    e4 = tree.nodes[root.children[0]]
    assert len(e4.children) == 2
    sans = {tree.nodes[node_id].san for node_id in e4.children}
    assert sans == {"e5", "c5"}
    exported = tree.export_pgn()
    assert "(1... c5)" in exported


def test_nested_variations_are_retained_without_flattening(scripted_gate):
    pgn = """[Event \"Nested variation test\"]
[Result \"*\"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. d3 (4. Nc3 d6 (4... Bc5 5. O-O d6) 5. d3 Be7 6. O-O O-O) 4... Bc5 5. O-O *
"""
    tree = import_pgn(scripted_gate, pgn, validate_root=True)
    exported = tree.export_pgn()
    assert "(4. Nc3 d6 (4... Bc5 5. O-O d6)" in exported
    assert exported.count("(") == 2
    assert exported.count(")") == 2
    assert len(tree.nodes) == 19
