# Litex Chess Studio v0.9.0

Litex Chess Studio 是一个面向**国际象棋规则学习、形式化审计和 Agent 交互**的 Litex 教材扩展。浏览器负责呈现与候选输入；Python 把具体局面编译成有限证书；Litex 对走子几何、局部棋盘变化、状态字段和王安全条件进行 fail-closed 核验。只要 Litex 缺失、超时、返回 unknown、解析失败或任一语句失败，本手棋就不会提交。

v0.9 的主要变化是：教材和工作台不再要求拥有自己的应用级页头、导航和侧栏，而是通过无 iframe Web Component 直接挂入 Litex Textbooks 页面。宿主 Litex 网站保留唯一的全局导航，Chess 扩展只渲染正文与互动区域。

## 1. 默认入口

本地启动后访问：

```text
Litex 教材页：  http://127.0.0.1:8000/textbook/Chess/position-state
棋局工作台：    http://127.0.0.1:8000/textbook/Chess/workbench
Playground 别名：http://127.0.0.1:8000/playground/chess
API 文档：      http://127.0.0.1:8000/docs
```

兼容调试页面仍保留：

```text
http://127.0.0.1:8000/standalone/textbook
http://127.0.0.1:8000/standalone/workbench
```

它们不再是默认官网集成入口。

## 2. 快速启动

### Windows

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
bash scripts/verify_release_v09.sh
bash scripts/run_dev.sh
```

Litex 固定版本见 `litex.lock`；开发包包含 Linux AMD64 与 Windows AMD64 可执行文件。

## 3. 嵌入 Litex 网站

加载一次扩展入口：

```html
<script type="module" src="/extensions/chess/embed/litex-chess-elements.js"></script>
```

在 Litex 正常教材正文容器中挂载章节：

```html
<litex-chess-textbook
  api-base="/api"
  source-base="/textbook-source"
  chapter-base="/textbook/Chess"
  workbench-base="/textbook/Chess/workbench"
  chapter="position-state">
</litex-chess-textbook>
```

或挂载工作台：

```html
<litex-chess-workbench
  api-base="/api"
  textbook-base="/textbook/Chess">
</litex-chess-workbench>
```

两个组件通过 Shadow DOM 隔离样式，但它们是宿主文档中的真实元素，**不使用 iframe**。宿主页面的路由、全局页头、教材目录和可访问性结构保持统一。

`integration/litex-site/register-chess.js` 提供框架无关的：

```js
registerLitexChess(host, options)
mountLitexChessRoute(outlet, route, options)
```

完整说明见 [`docs/LITEX_WEB_INTEGRATION_CN.md`](docs/LITEX_WEB_INTEGRATION_CN.md)。

公开 `golitex` 仓库提供验证器与教材源码结构，但当前生产网站实现并未随该仓库公开。本项目因此提供两层可合并交付：原生 `textbooks/Chess` 覆盖层，以及只依赖宿主正文容器/路由钩子的无 iframe Web Component 适配器；不会声称已经修改不可见的生产站点源码。

## 4. 原生 Litex 教材覆盖层

`integration/golitex-overlay/textbooks/Chess/` 可以复制到公开 `golitex` checkout 的 `textbooks/Chess/`：

```bash
python integration/install_into_golitex.py /path/to/golitex
/path/to/golitex/target/release/litex \
  -compact -runner -r /path/to/golitex/textbooks/Chess
```

覆盖层包含：

- module 风格 `litex.config`；
- 共享规则模块 `chess_rules.lit`；
- 十五个原生章节 `.lit` 文件；
- 交互扩展 manifest。

这些文件构成无 JavaScript 时仍可阅读、可运行的教材回退层；互动棋盘、完整证书和残局训练由 Web Component 增强。

## 5. 一手棋的执行链

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
    ├─ 是：提交新棋谱节点并保存源码/回执
    └─ 否：回滚，当前局面不变
```

机械候选不是合法性结论，只是把用户操作物化供证书核验。

## 6. Agent 可读的真实 Litex 记录

以 `e2e4` 为例，实际查询包含：

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

将杀着会记录：

```litex
by def $move(d8, h4)
by def $result(checkmate)
by def $result_witness(checkmate, 1, 0)
```

这些行与详细证书属于同一个 Litex 事务，不是界面伪代码。

## 7. 稀疏棋盘后继

生产查询不逐手重新比较全部 64 格。一手棋只登记实际变化的 2—4 格：

- 普通移动、吃子、升变：2 格；
- 吃过路兵：3 格；
- 王车易位：4 格。

定义精确棋盘码：

```text
BoardCode(B) = Σ (piece[i] + 6) · 16^i,  i = 0,…,63.
```

每个十六进制位使用 0–12，因此是可逆唯一展开，不是概率哈希。Litex 检查：

```text
after_code = before_code + Σ edit_contribution.
```

旧 64 格格式只作为历史兼容和差分审计工具保留。

## 8. 将军、将死与残局训练

有限状态分析从当前实际棋子出发生成候选，不枚举 `64×64` 格对。分类为：

```text
有将军 + 无合法应对 = checkmate
无将军 + 无合法应对 = stalemate
有将军 + 有合法应对 = check
否则                 = ongoing
```

它用于 SAN 的 `+/#`、终局教材和训练反馈，但不能单独批准工作台落子。固定回归包括：

```text
1. f3 e5 2. g4 Qh4#
```

内置互动课程包括：

- 单车杀王：建立盒子；
- 单车杀王：边线收官；
- 单后杀王：限制空间并避免逼和；
- 单马对单王死局；
- 单象对单王死局。

训练中的双方着法仍经过普通 Litex 门禁。

## 9. 十五章教材

1. 完整局面：棋盘、轮次、权利与 FEN；
2. 一手棋的可读记录、完整证书与稀疏后继；
3. 车、象与后：射线、阻挡和目标占用；
4. 马与王：跳跃、相邻格与受攻击目标；
5. 兵的方向、双步、斜吃与阻挡；
6. 升变、吃过路兵与王车易位；
7. 将军与三类应将；
8. 绝对牵制与相对牵制；
9. 闪击、闪将与双将；
10. 将死、逼和、死局与合法着集合；
11. 单马、单象、双马与“不能强杀/死局”的区别；
12. 重复局面、五十/七十五回合与棋局事件；
13. 王车与王后杀王的基本方法；
14. 互动基础残局训练；
15. Agent 记录、完整证书与可信边界。

## 10. 可信边界

Python 当前计算候选 `Position`、走子类型、路径和阻挡、稀疏编辑、元数据期望值、攻击者扫描、合法着集合与训练排序。Litex 核验具体坐标、棋子几何、特殊着条件、局部编辑、精确全盘码等式、FEN 元数据、王安全摘要和最终零失配合同。

当前架构因此是“宿主侧证书编译器 + Litex 核验器”，不是声称所有攻击关系和全局搜索已经从抽象棋盘中完全由 Litex 独立推导。

## 11. 目录结构

```text
backend/litex_chess/                    API、候选构造、证书、状态和训练
formal/chess_rules.lit                  唯一生产规则内核
research/formal/                        尚未进入运行时的研究蓝图
frontend/controllers/                   可挂载控制器
frontend/embed/                         无 iframe 自定义元素与内容片段
frontend/site/                          Litex 风格集成开发宿主
frontend/index.html,textbook.html       独立调试兼容页
textbook/                               中文镜像、课程目录与固定实验
integration/litex-site/                 网站路由/教材注册适配器
integration/golitex-overlay/            原生 textbooks/Chess 覆盖层
scripts/                                同步、启动、验证和打包
```

## 12. 验证与打包

```bash
python scripts/verify_release.py
bash scripts/package.sh /path/to/output
python scripts/package_litex_web_devkit.py /path/to/output
```

第一条归档包含固定版本验证器，第二条 `LitexWeb_DevKit` 是不携带平台二进制的轻量网站集成开发包。

门禁覆盖 Python、JavaScript、API、十五章教材、特殊着、将杀、残局、核心—教材同步、无 iframe 站点集成和原生 `textbooks/Chess` repository compile。结果写入：

```text
VERIFICATION_REPORT.md
verification/final/status.json
verification/generated/*.log
```
