# Litex Chess Studio v0.8 验证报告

- 生成时间：`2026-08-31T17:23:53.584350+00:00`
- 总体结果：**PASS**
- 生产棋盘后继：精确稀疏变更证书（2—4 格）
- 运行时规则源：`formal/chess_rules.lit`

| 检查项 | 含义 | 结果 | 退出码 | 秒 |
|---|---|---:|---:|---:|
| `textbook_sync` | 教材镜像与核心规则同步 | **PASS** | 0 | 3.355 |
| `python_compile` | Python 源码编译 | **PASS** | 0 | 2.348 |
| `python_tests` | 完整 Python 测试 | **PASS** | 0 | 4.255 |
| `frontend_contract` | 工作台与十五章教材静态契约 | **PASS** | 0 | 2.298 |
| `semantic_gate` | v0.8 语义门禁 | **PASS** | 0 | 3.447 |
| `api_smoke` | 工作台、教材、PGN 与终局 API 烟雾测试 | **PASS** | 0 | 11.534 |
| `textbook_examples` | 全部固定教材例与局面实验 | **PASS** | 0 | 15.101 |
| `js_app` | frontend/app.js 语法 | **PASS** | 0 | 0.185 |
| `js_notation` | frontend/notation.js 语法 | **PASS** | 0 | 0.335 |
| `js_textbook` | frontend/textbook.js 语法 | **PASS** | 0 | 0.183 |
| `notation_model` | 棋谱主变与括号变例模型 | **PASS** | 0 | 0.334 |
| `litex_version` | Litex 版本 | **PASS** | 0 | 0.021 |
| `litex_kernel` | 生产规则内核编译 | **PASS** | 0 | 0.332 |
| `litex_textbook` | 中文教材 Litex 编译 | **PASS** | 0 | 0.469 |
| `litex_research_contract` | 研究性证书契约编译 | **PASS** | 0 | 0.049 |
| `litex_research_blueprint` | 研究性全状态蓝图编译 | **PASS** | 0 | 0.081 |
| `legal_e2e4` | 合法 e2e4 | **PASS** | 0 | 1.990 |
| `fools_mate_qh4` | 愚人将杀 Qh4# | **PASS** | 0 | 2.090 |
| `illegal_e2e5` | 非法 e2e5 必须拒绝 | **PASS** | 2 | 2.138 |

## 覆盖范围

- 核心规则—中文教材单一事实源同步；
- Agent 可读 `move(...)`/`result(...)` 与完整 Litex 证书；
- 稀疏棋盘后继、FEN 元数据、王安全和最终接受合同；
- 愚人将杀、将死/逼和、重复局面、材料死局和残局训练接口；
- 棋谱主变纵排、旁支横排与括号嵌套；
- 15 章教材、19 个定义级例、22 个局面实验（45 条候选）、10 个状态实验和 5 个历史实验。

逐项原始输出位于 `verification/generated/`。
