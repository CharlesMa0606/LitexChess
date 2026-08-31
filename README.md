# Litex Chess Studio v0.8.0

Litex Chess Studio 是一个面向**国际象棋规则学习、形式化审计和 Agent 交互**的本地工作台。浏览器负责呈现与候选输入；Python 把具体局面编译成有限证书；Litex 对证书中的走子几何、局部棋盘变化、状态字段和王安全条件进行 fail-closed 核验。只要 Litex 缺失、超时、返回 unknown、解析失败或任一语句失败，本手棋就不会提交。

项目同时提供：

- 棋局工作台、线性主变与括号嵌套变例；
- 三层源码查看器：Agent 走法记录、完整 Litex 证书、固定规则内核；
- 十五章中文规则教材、正方形迷你棋盘、局面实验与历史实验；
- 将军、将死、逼和、牵制、闪将、双将、重复局面和回合规则示例；
- 王车杀王、王后杀王以及单马/单象死局的互动训练；
- PGN 导入导出、FEN 状态追踪和每节点证书回执。

> 本项目仍是研究与教学原型。它没有调用 Stockfish 等普通棋规引擎作为接受兜底，也不宣称当前 Python 可信计算基已经全部下沉到 Litex。

## 1. 快速启动

### Windows

解压代码包，在项目目录依次运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify_windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_windows.ps1
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
chmod +x tools/litex/linux-amd64/litex
export LITEX_BIN="$PWD/tools/litex/linux-amd64/litex"
export LITEXPY_LITEX_BIN="$LITEX_BIN"
bash scripts/verify_release_v08.sh
bash scripts/run_dev.sh
```

启动后访问：

```text
棋局工作台：http://127.0.0.1:8000
规则教材：  http://127.0.0.1:8000/textbook
API 文档：  http://127.0.0.1:8000/docs
```

Litex 固定版本见 `litex.lock`；代码包自带 Linux AMD64 与 Windows AMD64 可执行文件。

## 2. 一手棋的真实执行链

```text
当前 Position
    │  board + turn + castling + ep + halfmove + fullmove
    ▼
用户提交 Move(source, target, promotion)
    ▼
candidate.py 机械构造候选后继
    ▼
query.py 独立重算几何、路径、稀疏后继、元数据和王安全摘要
    ▼
生成同一 Litex 事务
    ├─ Agent 可读封面
    └─ 完整有限证书
    ▼
Litex 全部接受？
    ├─ 是：提交新棋谱节点，并保存源码/回执
    └─ 否：回滚，当前局面不变
```

机械候选不是合法性结论。它只是把“用户想做的操作”物化出来，供随后证书核验。

## 3. Agent 可读的真实 Litex 记录

以 `e2e4` 为例，完整查询开头包含：

```litex
# [agent-record:start]
have e2 Z = 12
have e4 Z = 28
have ongoing Z = 0
by def $square(5, 2, e2)
by def $square(5, 4, e4)
by def $move(e2, e4)
by def $promotion_choice(0)
by def $result(ongoing)
by def $result_witness(ongoing, 0, 20)
# move=e2e4; result=ongoing; checkers=0; legal_replies=20
# [agent-record:end]
```

将杀着会记录为：

```litex
by def $move(d8, h4)
by def $result(checkmate)
by def $result_witness(checkmate, 1, 0)
```

这些行并非界面伪代码，而是实际 Litex 事务的一部分。其后仍有完整证书；任何后续失败都会使整手棋被拒绝。

工作台的源码面板分为：

1. **Agent 走法记录**：接近普通走子记录的封面；
2. **完整 Litex 证书**：几何、路径、稀疏棋盘、元数据、王安全与最终合同；
3. **固定规则内核**：运行时真正加载的 `formal/chess_rules.lit`。

## 4. 棋盘后继：稀疏变更而非每手重比 64 格

生产模式把棋盘看作不可变前态加规范化局部编辑：

- 普通移动、吃子或升变：2 个格子；
- 吃过路兵：3 个格子；
- 王车易位：4 个格子。

例如 `e2e4` 只描述：

```text
e2：白兵 → 空格
e4：空格 → 白兵
```

为证明没有遗漏其他格子的变化，定义精确棋盘码

```text
BoardCode(B) = Σ (piece[i] + 6) · 16^i,  i = 0,…,63.
```

每个十六进制位只使用 0–12，因此这是可逆的唯一展开，不是概率哈希。Litex 检查：

```text
after_code = before_code + Σ edit_contribution.
```

旧版逐格比较已经移出生产内核；`compact_transition.py` 只保留对历史查询夹具的兼容转换和差分审计能力。

## 5. FEN 与历史状态

每个节点保存完整 `Position`：

```text
board[64]
turn
castling
ep_square
halfmove
fullmove
```

FEN 是该对象的序列化结果，不是另一个合法性引擎。易位权和有效吃过路兵权带有历史信息，不能仅从棋子摆放恢复；因此两张看起来相同的棋盘可能不是重复规则意义上的“同一局面”。

## 6. 将军、将死和合法着集合

`fast_state.py` 从当前实际棋子出发，按棋子类型生成精确伪合法候选，再过滤暴露本方王的着法。它不再枚举全部 `64×64` 源格—目标格组合。

状态分类为：

```text
有将军 + 无合法应对 = checkmate
无将军 + 无合法应对 = stalemate
有将军 + 有合法应对 = check
否则                 = ongoing
```

该有限集合分析用于 SAN 的 `+/#`、终局教材和训练反馈；它**不能单独批准工作台落子**。真正写入棋谱树的每一手仍须经过 Litex 门禁。

固定回归包含愚人将杀：

```text
1. f3 e5 2. g4 Qh4#
```

## 7. 十五章规则教材

教材按照学习顺序组织：

1. 完整局面：棋盘、轮次、权利与 FEN；
2. 一手棋的可读记录、完整证书与稀疏后继；
3. 车、象与后：射线、阻挡和目标占用；
4. 马与王：跳跃、相邻格与受攻击目标；
5. 兵的方向、双步、斜吃与阻挡；
6. 升变、吃过路兵与王车易位；
7. 将军与三类应将：移王、吃子、挡线；
8. 绝对牵制与相对牵制；
9. 闪击、闪将与双将；
10. 将死、逼和、死局与合法着集合；
11. 单马、单象、双马与“不能强杀/死局”的区别；
12. 重复局面、五十/七十五回合与棋局事件；
13. 王车与王后杀王的基本方法；
14. 互动基础残局训练；
15. Agent 走法记录、完整证书与可信边界。

教材的中文注释 Litex 文件由 `scripts/sync_textbook_core.py` 从生产内核确定性生成。发布门禁比较两份文件的完整非注释定义流，不依赖固定行数。

迷你棋盘与残局棋盘均采用 `8×8` 等分网格和 `aspect-ratio: 1`；棋子、坐标和教学文字位于独立叠层，不参与格子尺寸计算。

## 8. 互动残局训练

内置课程：

- 单车杀王：建立盒子；
- 单车杀王：边线收官；
- 单后杀王：限制空间并避免逼和；
- 单马对单王：规则意义上的死局；
- 单象对单王：规则意义上的死局。

训练中的学习者着法和自动防守着都调用普通 `Gate.validate_move`。系统的提示与防守排序是教学启发式，不宣称表库最短将杀或最优博弈。

## 9. 可信边界

### Python 当前负责计算

- 候选 `Position`；
- 走子类型选择、滑行路径与阻挡数；
- 规范化稀疏编辑及精确棋盘码参数；
- FEN 元数据期望值；
- 当前版本的攻击者扫描；
- 合法着集合、重复键和教材战术标签；
- 自动防守候选的排序。

### Litex 当前直接核验

- 坐标、棋子和行棋方编码；
- 选定棋子几何与特殊走法条件；
- 路径无阻挡；
- 2—4 个局部编辑及全盘码增量等式；
- 易位权、吃过路兵、回合计数等元数据一致性；
- 给定王数量和攻击计数满足安全合同；
- 最终 `legal_transition` 的零失配条件。

因此当前架构是“宿主侧证书编译器 + Litex 核验器”，而不是 Litex 已经从一个抽象棋盘映射中独立枚举并证明所有关系。研究性全状态关系接口位于 `research/formal/`，不会被生产运行时加载。

## 10. 目录结构

```text
backend/litex_chess/       服务、候选构造、证书生成、状态分析和残局训练
formal/chess_rules.lit     唯一生产规则内核
research/formal/           尚未进入运行时的关系化研究蓝图
frontend/                  工作台与教材前端
textbook/                  中文 Litex 镜像和十五章目录
samples/                   PGN 示例
scripts/                   启动、同步、验证和打包脚本
tools/litex/               固定平台 Litex 可执行文件
verification/              发布门禁报告和逐项日志
```

## 11. 验证与打包

运行完整门禁：

```bash
python scripts/verify_release.py
```

门禁覆盖：

- Python 单元测试与语法；
- 前端 JavaScript 语法及静态契约；
- 核心—教材镜像同步；
- 固定教材例、局面、状态和历史实验；
- 工作台、PGN、源码查看和残局 API 烟雾测试；
- 愚人将杀、特殊走法与非法着回滚；
- 生产内核、中文教材和研究蓝图的 Litex 编译。

打包：

```bash
bash scripts/package.sh /path/to/output
```

发布包内的 `VERIFICATION_REPORT.md` 与 `verification/final/status.json` 给出本次实际门禁结果。
