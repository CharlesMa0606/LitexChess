from litex_chess.compact_transition import compact_query_source

def test_compact_runtime_transform_is_stable_and_idempotent():
    src='# before_fen: 8/8/8/8/8/8/4P3/4K3 w - - 0 1\n# after_fen: 8/8/8/8/4P3/8/8/4K3 b - e3 0 1\n' + '\n'.join('by def $chess_rules::board_rank_transition('+','.join(['0']*16)+')' for _ in range(8))
    one=compact_query_source(src,mode='compact')
    two=compact_query_source(one,mode='compact')
    assert 'board_rank_transition' not in one
    assert one==two
    assert 'sparse_board_transition' in one
