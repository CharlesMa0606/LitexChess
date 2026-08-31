from __future__ import annotations
from pathlib import Path
import json
from litex_chess.textbook import mirror_report

ROOT=Path(__file__).resolve().parents[2]
CORE=ROOT/'formal/chess_rules.lit'
TEXTBOOK=ROOT/'textbook/chess_rules_textbook_cn.lit'

def _chapters():
    data=json.loads((ROOT/'textbook/chapters.json').read_text(encoding='utf-8'))
    if isinstance(data,list): return data
    for key in ('chapters','items','lessons'):
        if isinstance(data.get(key),list): return data[key]
    raise AssertionError('chapter list missing')

def test_textbook_definition_mirror_is_exact_before_examples():
    report=mirror_report(CORE,TEXTBOOK)
    assert report['in_sync'] is True, report.get('first_difference')
    assert report['core_sha256']==report['textbook_sha256']
    assert report.get('core_line_count',report.get('core_lines'))==report.get('textbook_line_count',report.get('textbook_lines'))

def test_curriculum_has_fifteen_coherent_chapters_and_endgames():
    chapters=_chapters()
    assert len(chapters)==15
    blob=json.dumps(chapters,ensure_ascii=False)
    for phrase in ('完整局面','阻挡','将军','牵制','闪将','双将','将死','逼和','三次重复','五十回合','王车','王后','单马','互动基础残局训练','Agent','可信边界'):
        assert phrase in blob

def test_runtime_rule_source_is_explicit_and_research_is_separate():
    assert (ROOT/'formal/RUNTIME_KERNEL.txt').read_text(encoding='utf-8').strip()=='chess_rules.lit'
    research=ROOT/'research/formal'
    assert (research/'certificate_contract.lit').exists()
    assert (research/'chess_specification_full.lit').exists()
    assert not (ROOT/'formal/certificate_contract.lit').exists()
    assert not (ROOT/'formal/chess_specification_full.lit').exists()
