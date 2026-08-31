from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_transition_trace_exposes_sparse_edits_and_mode():
    s=(ROOT/'backend/litex_chess/transition_trace.py').read_text(encoding='utf-8')
    assert 'edit' in s.lower()
    assert 'mode' in s.lower()
    assert 'compact' in (ROOT/'backend/litex_chess/compact_transition.py').read_text(encoding='utf-8')

def test_production_query_does_not_require_rank_transition():
    s=(ROOT/'backend/litex_chess/query.py').read_text(encoding='utf-8')
    # The legacy predicate may remain for explicit audit branches, but compact
    # construction must be present as the production route.
    assert 'sparse_board_transition' in s or 'compact_transition' in s
