#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys,json,inspect,re,os
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
errors=[]
def check(cond,msg):
    if not cond: errors.append(msg)

# Single-source mirror.
from litex_chess.textbook import mirror_report
mr=mirror_report(ROOT/'formal/chess_rules.lit',ROOT/'textbook/chess_rules_textbook_cn.lit')
check(bool(mr.get('in_sync')),f'mirror mismatch: {mr.get("first_difference")}')
check(mr.get('core_sha256')==mr.get('textbook_sha256'),'mirror sha mismatch')

# Curriculum.
data=json.loads((ROOT/'textbook/chapters.json').read_text(encoding='utf-8'))
chapters=data if isinstance(data,list) else next((data[k] for k in ('chapters','items','lessons') if isinstance(data.get(k),list)),[])
check(len(chapters)==15,f'expected 15 chapters, got {len(chapters)}')
blob=json.dumps(chapters,ensure_ascii=False)
for phrase in ('互动基础残局训练','王车','王后','单马','Agent','可信边界'):
    check(phrase in blob,f'curriculum missing {phrase}')

# Runtime/research separation.
check((ROOT/'formal/RUNTIME_KERNEL.txt').read_text(encoding='utf-8').strip()=='chess_rules.lit','runtime kernel manifest')
check((ROOT/'research/formal/certificate_contract.lit').exists(),'research contract missing')
check((ROOT/'research/formal/chess_specification_full.lit').exists(),'research blueprint missing')
check(not (ROOT/'formal/certificate_contract.lit').exists(),'research contract still in runtime root')
check(not (ROOT/'formal/chess_specification_full.lit').exists(),'research blueprint still in runtime root')

# Native Litex-site integration plus standalone compatibility bootstraps.
index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
app_js = (ROOT / "frontend/controllers/workbench.js").read_text(encoding="utf-8")
textbook_html = (ROOT / "frontend/textbook.html").read_text(encoding="utf-8")
textbook_js = (ROOT / "frontend/controllers/textbook.js").read_text(encoding="utf-8")
textbook_css = (ROOT / "frontend/textbook.css").read_text(encoding="utf-8")
for phrase in ("Agent 走法记录", "完整 Litex 证书", "固定规则内核"):
    check(phrase in index, f"workbench missing tab {phrase}")
check("receiptAgentSource" in app_js, "workbench does not expose the actual Agent record")
for phrase in ("renderEndgameLabs", "startEndgameLesson", "playEndgameMove", "endgameWorkbenchUrl"):
    check(phrase in textbook_js, f"textbook native integration missing {phrase}")
check("endgameLabsSection" in textbook_html, "textbook endgame section missing")
check("aspect-ratio: 1" in textbook_css or "aspect-ratio:1" in textbook_css, "trainer board is not square")
check("v08_integration" not in index + textbook_html, "obsolete integration bridge still referenced")
check((ROOT / "frontend/site/index.html").exists(), "Litex host preview missing")
check((ROOT / "frontend/embed/litex-chess-elements.js").exists(), "custom-element entry missing")
site_blob = (ROOT / "frontend/site/index.html").read_text(encoding="utf-8") + (ROOT / "frontend/embed/litex-chess-elements.js").read_text(encoding="utf-8")
check("litex-site-header" in site_blob, "integrated host shell missing")
check("litex-chess-textbook" in site_blob and "litex-chess-workbench" in site_blob, "embedded components missing")
check("<iframe" not in site_blob.lower(), "integration unexpectedly uses iframe")
check(not (ROOT / "frontend/v08_integration.js").exists(), "obsolete integration JS still packaged")
check(not (ROOT / "backend/litex_chess/v08_endgame_api.py").exists(), "obsolete endgame route adapter still packaged")

# All curriculum endgame IDs must resolve to the one backend catalogue.
try:
    from litex_chess.endgame_training import LESSONS
    check(len(LESSONS) == 5, f"expected 5 unique endgame lessons, got {len(LESSONS)}")
    referenced = set()
    for chapter in chapters:
        referenced.update(chapter.get("endgame_courses", []))
        referenced.update(chapter.get("interactive_endgames", []))
    check(referenced <= set(LESSONS), f"unknown curriculum endgames: {sorted(referenced - set(LESSONS))}")
except Exception as exc:
    errors.append(f"endgame catalogue import failed: {type(exc).__name__}: {exc}")

# Agent-facing markers must occur in an actual generated query, not merely in
# frontend display code or comments.  The record generator is deliberately a
# separate module from the detailed certificate compiler.
try:
    from litex_chess.candidate import apply_candidate
    from litex_chess.model import Move, Position
    from litex_chess.query import LitexQueryBuilder

    builder = LitexQueryBuilder.from_file(ROOT / 'formal/chess_rules.lit')
    built = builder.build_move_query(
        apply_candidate(Position.initial(), Move.from_uci('e2e4'))
    )
    for phrase in ('$move(e2, e4)', '$result(', 'agent-record:start'):
        check(phrase in built.source, f'actual generated query missing {phrase}')
        check(phrase in built.agent_source, f'Agent view missing {phrase}')
    check(built.agent_source.strip() in built.source,
          'Agent record is not part of the same Litex transaction')
except Exception as exc:
    errors.append(f'actual Agent query generation failed: {type(exc).__name__}: {exc}')

core=(ROOT/'formal/chess_rules.lit').read_text(encoding='utf-8')
check(re.search(r'\bprop\s+move\b',core) is not None,'kernel missing move proposition')
check(re.search(r'\bprop\s+result\b',core) is not None,'kernel missing result proposition')

# Compact transformer must execute without recursive wrapping and omit legacy rank checks in compact mode.
try:
    from litex_chess.compact_transition import compact_query_source
    synthetic='''# before_fen: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1\n# after_fen: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1\nby def $chess_rules::board_rank_transition(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)\n'''
    out=compact_query_source(synthetic,mode='compact')
    check('board_rank_transition' not in out,'compact query retained legacy rank transition')
except Exception as exc:
    errors.append(f'compact transform failed: {type(exc).__name__}: {exc}')

# Dynamic checkmate analysis through the exact finite state generator used by
# the query/SAN layer.
try:
    from litex_chess.fast_state import analyze_fen
    fen='rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3'
    rd=analyze_fen(fen)
    status=str(rd.get('status','')).lower()
    legal=rd.get('legal_count')
    check(status=='checkmate',f'Fool mate status={status!r}')
    check(int(legal)==0,f'Fool mate legal replies={legal}')
    check(bool(rd.get('in_check')), 'Fool mate must be in check')
except Exception as exc:
    errors.append(f'Fool mate dynamic analysis failed: {type(exc).__name__}: {exc}')

# Endgame training code/catalog must exist.
e=(ROOT/'backend/litex_chess/endgame_training.py')
check(e.exists(),'endgame training module missing')
if e.exists():
    eb=e.read_text(encoding='utf-8').lower()
    for phrase in ('rook','queen','knight'):
        check(phrase in eb,f'endgame module missing {phrase}')

if errors:
    print('V0.9 SEMANTIC GATE: FAIL')
    for e in errors: print('- '+e)
    raise SystemExit(1)
print('V0.9 SEMANTIC GATE: PASS')
print(f'mirror executable lines: {mr.get("core_line_count",mr.get("core_lines"))}')
print('chapters: 15')
