#!/usr/bin/env python3
"""Regenerate the Chinese textbook mirror from the canonical Litex kernel.

The runtime kernel is the single source of truth.  This script inserts Chinese
teaching commentary and source-module markers *around* contiguous slices of the
kernel; it never retypes or edits a core Litex statement.  Consequently the
non-comment lines before the explicit examples boundary are byte-for-byte equal
to ``formal/chess_rules.lit`` after comments/blank lines are removed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "formal" / "chess_rules.lit"
TEXTBOOK = ROOT / "textbook" / "chess_rules_textbook_cn.lit"

MODULES = [
    (
        "encoding",
        "源码模块 A　局面、格名与 Agent 走法记录",
        """局面首先由完整 Position 表示，而不是只有一张棋盘图片。核心在这里定义
棋盘坐标、棋子编码、通用 square(file, rank, index) 映射，以及 move/result
接口。每条查询只为本手涉及的格子和结果创建局部可读别名：

    have e2 Z = 12
    have e4 Z = 28
    have ongoing Z = 0
    by def $square(5, 2, e2)
    by def $square(5, 4, e4)
    by def $move(e2, e4)
    by def $result(ongoing)

result_witness(ongoing, 0, 20) 位于详细证书中，给出将军者数量与合法应对数。
这样无需在内核中永久维护 a1--h8 的 64 个全局常量。可读封面与后面的
详细证书属于同一次 Litex 事务；后续任一事实失败，整手棋都不会被提交。""",
        None,
        "prop coordinate(",
    ),
    (
        "lifecycle",
        "源码模块 B　一手棋的前置条件与棋盘后继接口",
        """浏览器只提交 from/to/promotion。candidate.py 机械构造候选 Position，
query.py 独立重算形状、局部变更、元数据和王安全证书，Litex 最后决定是否接受。

本段只保留当前走法真正需要的坐标、棋子归属与路径前置条件。棋盘后继不再
维护一套 64 格逐项相等接口；模块 H 使用 2--4 个稀疏编辑和精确全盘码，直接表达
“本手究竟修改了哪些格子”。""",
        "prop coordinate(",
        "prop pawn_single_move(",
    ),
    (
        "pawn",
        "源码模块 C　兵的五类走法",
        """兵必须分开处理单步、初始双步、斜吃、升变和吃过路兵。白兵 side=1，
黑兵 side=-1，使前进方向可以用同一组整数关系表达。迷你棋盘实验会同时展示目标格、
双步经过格、过路兵被删除格以及升变选择，避免把规则压缩成一句无法理解的调用。""",
        "prop pawn_single_move(",
        "prop knight_move(",
    ),
    (
        "pieces",
        "源码模块 D　马、象、车、后与王",
        """马只检查 (1,2)/(2,1) 的坐标差；象、车、后还需要宿主侧给出的路径阻挡数为零；
王的一步几何与“走后是否受攻击”分层检查。这样可以清楚区分：几何上像一手棋，
与整手棋在完整局面中合法，是两个不同命题。""",
        "prop knight_move(",
        "prop white_kingside_castle(",
    ),
    (
        "castling",
        "源码模块 E　王车易位",
        """易位依赖历史权利、路径占用以及起点/经过格/终点的王安全。王或原始角车移动后，
权利永久删除；即使棋子回到原位也不会恢复。四个谓词分别处理双方王翼与后翼易位，
而 FEN 的 KQkq 字段承担这部分不可从棋盘摆放恢复的历史记忆。""",
        "prop white_kingside_castle(",
        "# The concrete runtime currently computes attacking pieces",
    ),
    (
        "safety",
        "源码模块 F　攻击关系、王安全与结构不变量",
        """当前具体运行时由 Python 枚举攻击者并传入计数，Litex 检查 king_safe 所需的
“唯一王且不安全攻击者为零”。更抽象的 attack-relation 试验已移到 research/formal，
不会与生产棋规混在一起。绝对牵制、闪将、双将等教学标签来自同一攻击扫描，
但不会另行改写合法性。""",
        "# The concrete runtime currently computes attacking pieces",
        "prop metadata_transition(",
    ),
    (
        "metadata",
        "源码模块 G　FEN 元数据更新",
        """一手棋除了改变棋盘，还必须更新行棋方、KQkq、过路兵目标、halfmove 与 fullmove。
metadata_transition 对候选值和独立期望值逐项做等式检查。重复局面、五十回合等跨节点
规则则在已提交 Position 的历史时间线上计算，不能由当前单手的局部谓词代替。""",
        "prop metadata_transition(",
        "prop legal_transition(",
    ),
    (
        "contract",
        "源码模块 H　总合同与精确稀疏棋盘变更",
        """生产表示把棋盘视为不可变对象。一手普通着只列出源格和目标格，吃过路兵列出三格，
易位列出四格。每格编辑给出 (after-before)*16^index 的精确贡献；所有贡献必须把走前
全盘的无碰撞十六进制编码变成实际走后编码。由此排除未登记的第五个改动，而无需每次
逐格复述其余 60--62 个不变格。legal_transition 再汇总形状、棋盘、元数据和王安全。""",
        "prop legal_transition(",
        None,
    ),
]

HEADER = """# Litex Chess Studio 国际象棋规则教材（自动同步的中文注释镜像）
#
# 单一事实源与运行边界：
# 1. 实际落子只加载 formal/chess_rules.lit；本教材不替换运行时内核。
# 2. 本文件由 scripts/sync_textbook_core.py 生成。前 8 个源码模块只在核心原文周围
#    插入中文注释和章节标记；所有非注释 Litex 行与核心逐行一致。
# 3. examples 模块位于显式边界之后，只包含固定教学正例。
# 4. 网页教材按 15 章、6 部组织，并通过同一工作台与 Litex 门禁完成局面和残局训练。
# 5. Agent 视图显示同一次查询中真正被检查的 move(...)、result(...) 可读封面；
#    完整证书视图继续公开稀疏棋盘、元数据、王安全与总合同。
#
"""

EXAMPLES = """# [chapter:examples:start]
# 源码模块 I　定义级显微镜与 Agent 可读封面
#
# 这些 by def 只展示单个谓词如何展开；完整落子还需要同一查询中的棋子形状、
# 稀疏棋盘后继、FEN 元数据、王安全和最终总合同。网页的“局面实验室”和
# “互动残局训练”会走与工作台完全相同的接口。

# e2-e4 的 Agent 可读封面。格名与结果名都是本次查询的局部别名。
have e2 Z = 12
have e4 Z = 28
have ongoing Z = 0
by def $square(5, 2, e2)
by def $square(5, 4, e4)
by def $move(e2, e4)
by def $result(ongoing)
by def $result_witness(ongoing, 0, 20)

# 初始局面 e2-e4 的兵双步局部形状。
by def $pawn_double_move(1, 0, 0, 1, 5, 2, 5, 4, 0)

# g1-f3 的白马局部形状。
by def $knight_move(2, 0, 1, 7, 1, 6, 3, 0)

# 两个局部编辑可组成精确棋盘增量（这里用小整数示意）。
by def $sparse_square_edit(0, 4, 0, 1, -4)
by def $sparse_square_edit(1, 0, 4, 16, 64)
by def $sparse_board_transition(100, 160, -4, 64, 0, 0, 2, 0, 0, 0)

# 白方短易位的局部参数全部满足。
by def $white_kingside_castle(6, 0, 0, 4, 1, 5, 1, 7, 1, 0, 1, 1, 1)

# FEN 元数据候选值与期望值逐项一致。
by def $metadata_transition(-1, -1, 1, 1, 1, 1, 1, 1, 1, 1, 5, 5, 3, 3, 0, 0, 1, 1)

# 最终总合同全部汇总为零差异。
by def $legal_transition(1, 0, 0, 1, 1, 1, 1, 0, 0)
# [chapter:examples:end]

# 阅读顺序：Agent 记录 → 走子形状 → 2--4 个稀疏编辑与精确全盘码 →
# FEN 元数据 → 王安全 → legal_transition。终局与历史结论还要查看合法着集合、
# 重复身份键和回合计数器；它们不会被一条 move(...) 语句偷换掉。
"""


def locate(source: str, marker: str | None, *, default: int) -> int:
    if marker is None:
        return default
    index = source.find(marker)
    if index < 0:
        raise ValueError(f"core marker not found: {marker}")
    # Start at the beginning of the marker's line.
    return source.rfind("\n", 0, index) + 1


def generate() -> str:
    core = CORE.read_text(encoding="utf-8").rstrip() + "\n"
    pieces: list[str] = [HEADER.rstrip(), ""]
    previous_end = 0
    for slug, title, explanation, start_marker, end_marker in MODULES:
        start = locate(core, start_marker, default=0)
        end = locate(core, end_marker, default=len(core))
        if start != previous_end:
            # Markers are deliberately contiguous; a gap would risk reordering
            # or silently dropping a core statement.
            raise ValueError(
                f"non-contiguous core slices before {slug}: expected {previous_end}, got {start}"
            )
        if end <= start:
            raise ValueError(f"empty or reversed source slice for {slug}")
        pieces.extend(
            [
                f"# [chapter:{slug}:start]",
                f"# {title}",
                "#",
                *[f"# {line}" if line else "#" for line in explanation.splitlines()],
                "",
                core[start:end].rstrip(),
                f"# [chapter:{slug}:end]",
                "",
            ]
        )
        previous_end = end
    if previous_end != len(core):
        raise ValueError(f"core tail not mirrored: stopped at {previous_end} of {len(core)} bytes")
    pieces.append(EXAMPLES.rstrip())
    return "\n".join(pieces).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the mirror is stale")
    args = parser.parse_args()
    generated = generate()
    current = TEXTBOOK.read_text(encoding="utf-8") if TEXTBOOK.exists() else ""
    if args.check:
        if current != generated:
            print("textbook_mirror=STALE")
            return 1
        print("textbook_mirror=SYNC")
        return 0
    TEXTBOOK.write_text(generated, encoding="utf-8")
    print(f"wrote {TEXTBOOK.relative_to(ROOT)} ({len(generated.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
