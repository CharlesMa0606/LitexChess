# Litex Chess Studio v0.8.0 发布说明

## 本版目标

v0.8.0 把工作台、规则教材、Agent 接口和残局训练收束到同一条 Litex 核验链，并清理了旧版手工镜像、64 格生产查询、临时前端桥接和重复状态分析代码。

## 1. 单一生产规则源

运行时只加载：

```text
formal/chess_rules.lit
```

中文教材镜像由：

```text
scripts/sync_textbook_core.py
```

确定性生成。发布门禁按完整非注释定义流比较核心与教材，不再使用固定的“229 行/322 行”假设。研究性的全状态关系和证书蓝图位于 `research/formal/`，不会被误加载为生产棋规。

## 2. Agent 可读记录进入真实事务

每手查询首先给出接近普通记录的 Litex 封面：

```litex
by def $move(e2, e4)
by def $promotion_choice(0)
by def $result(ongoing)
by def $result_witness(ongoing, 0, 20)
```

随后展开棋子几何、路径、稀疏后继、FEN 元数据、王安全与最终合同。封面和详细证书属于同一事务；后半段失败时，本手不会提交。

工作台源码区域分为：

- Agent 走法记录；
- 完整 Litex 证书；
- 固定规则内核。

## 3. 精确稀疏棋盘后继

生产查询不再为每手棋重复列出 64 个格子等式。一手棋只登记实际变化的 2—4 格，并使用无碰撞的十六进制全盘码检查没有遗漏其他变化：

```text
BoardCode(after) = BoardCode(before) + Σ local_edit.
```

旧逐格格式仅保留为历史查询夹具的兼容/差分审计工具，不再属于生产内核。

## 4. 将死结果统一

SAN、Agent `result(...)`、工作台状态和教材终局实验读取同一份有限合法着分析。愚人将杀固定回归为：

```text
1. f3 e5 2. g4 Qh4#
```

最后局面必须满足：

```text
status = checkmate
checker_count = 1
legal_reply_count = 0
```

状态分析从当前棋子出发生成候选，不枚举 4096 个源格—目标格组合。它用于集合级汇总，不替代单手 Litex 接受权威。

## 5. 工作台与教材联动

教材局面和残局课程可携带 FEN、课程名和学习目标打开工作台。工作台加载相同的完整 `Position`，落子仍调用普通 Litex 门禁。教材不再维护一套独立的浏览器棋规。

## 6. 十五章教材与互动残局

教材调整为十五章，覆盖：

- 棋盘状态与 FEN；
- 全部棋子走法、阻挡和特殊着；
- 将军、应将、牵制、闪将与双将；
- 将死、逼和、材料死局、重复和回合规则；
- 王车/王后杀王方法；
- 教材内互动残局；
- Agent 记录、完整证书和可信边界。

互动课程包括单车、单后杀王以及单马/单象对单王死局。双方实际训练着法都由同一 Litex 门禁处理。

## 7. 代码整理

本版移除了：

- 手工维护的规则镜像；
- 生产内核中的逐格后继谓词；
- 临时 `v08_integration.js/css` 桥接层；
- 重复的 `v08_state.py` 与查询后处理器；
- 旧版固定章节数、固定镜像行数和过时前端断言；
- 旧版本截图与失败验证产物。

## 8. 验证

`python scripts/verify_release.py` 会生成：

```text
VERIFICATION_REPORT.md
verification/final/status.json
verification/generated/*.log
```

验证包括核心—教材同步、Python/JavaScript、Litex 编译、完整教材实验、API、PGN、特殊着、将杀和残局训练流程。最终发布压缩包还会重新解压并复跑关键门禁。
