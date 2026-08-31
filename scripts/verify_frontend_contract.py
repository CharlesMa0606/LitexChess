#!/usr/bin/env python3
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
errors=[]
def need(cond,msg):
    if not cond: errors.append(msg)
idx_html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
app=(ROOT/'frontend/app.js').read_text(encoding='utf-8')
tb_html=(ROOT/'frontend/textbook.html').read_text(encoding='utf-8')
tb_js=(ROOT/'frontend/textbook.js').read_text(encoding='utf-8')
css=''.join((ROOT/'frontend/textbook.css').read_text(encoding='utf-8').split())
for x in ('Agent 走法记录','完整 Litex 证书','固定规则内核'):
    need(x in idx_html,'workbench source tab '+x)
for x in ('receiptAgentSource','formalMode','/api/formal/source','URLSearchParams','resolveWorkbenchContext'):
    need(x in app,'workbench integration '+x)
for x in ('endgameLabsSection','互动残局训练'):
    need(x in tb_html,'textbook endgame section '+x)
need('endgameTrainerPanel' in tb_js,'textbook endgame trainer panel')
for x in ('endgameWorkbenchUrl','/api/textbook/endgames/','/api/textbook/endgame-sessions/','URLSearchParams','fen'):
    need(x in tb_js,'textbook integration '+x)
need('grid-template-columns:repeat(8' in css,'8 equal board columns')
need('grid-template-rows:repeat(8' in css,'8 equal board rows')
need('aspect-ratio:1' in css,'square board')
data=json.loads((ROOT/'textbook/chapters.json').read_text(encoding='utf-8'))
chapters=data if isinstance(data,list) else next((data[k] for k in ('chapters','items','lessons') if isinstance(data.get(k),list)),[])
need(len(chapters)==15,f'15 chapters, got {len(chapters)}')
need(any(ch.get('endgame_courses') or ch.get('interactive_endgames') for ch in chapters),'curriculum has no endgame course')
if errors:
    print('FRONTEND CONTRACT FAIL')
    for e in errors: print('- '+e)
    sys.exit(1)
print('FRONTEND CONTRACT PASS')
