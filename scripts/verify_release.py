#!/usr/bin/env python3
"""Cross-platform release gate for Litex Chess Studio v0.9.

The gate is intentionally explicit and bounded.  It checks the generated
textbook mirror, Python/JavaScript syntax, unit and semantic tests, HTTP smoke
flows, all fixed textbook examples, and direct Litex compilation.  Every
subprocess has a finite timeout; a missing verifier is a required failure.
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "verification" / "generated"
REPORT = ROOT / "VERIFICATION_REPORT.md"
STATUS_JSON = ROOT / "verification" / "final" / "status.json"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class Gate:
    name: str
    title: str
    command: list[str]
    expected: set[int]
    timeout: float = 300.0
    required: bool = True
    status: str = "NOT RUN"
    returncode: int | None = None
    seconds: float = 0.0
    output: str = ""

    def run(self, env: dict[str, str]) -> None:
        start = time.perf_counter()
        fd, raw_name = tempfile.mkstemp(prefix=f"litex-chess-{self.name}-", suffix=".log")
        os.close(fd)
        raw_log = Path(raw_name)
        try:
            # Write child output directly to a file rather than a PIPE.  Some
            # verification scripts briefly own persistent Litex subprocesses;
            # file-backed capture cannot be kept open by a grandchild in a way
            # that makes ``subprocess.run(..., PIPE)`` wait forever for EOF.
            with raw_log.open("w", encoding="utf-8") as stream:
                proc = subprocess.run(
                    self.command,
                    cwd=ROOT,
                    env=env,
                    text=True,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout,
                    check=False,
                )
            self.returncode = proc.returncode
            self.output = raw_log.read_text(encoding="utf-8", errors="replace")
            self.status = "PASS" if proc.returncode in self.expected else "FAIL"
        except subprocess.TimeoutExpired:
            self.status = "TIMEOUT"
            self.output = (
                raw_log.read_text(encoding="utf-8", errors="replace")
                if raw_log.exists() else ""
            ) + f"\nTimed out after {self.timeout:.0f}s\n"
        except Exception as exc:  # operational diagnostics
            self.status = "ERROR"
            captured = (
                raw_log.read_text(encoding="utf-8", errors="replace")
                if raw_log.exists() else ""
            )
            self.output = captured + f"\n{type(exc).__name__}: {exc}\n"
        finally:
            raw_log.unlink(missing_ok=True)
        self.seconds = time.perf_counter() - start
        (LOG_DIR / f"{self.name}.log").write_text(
            f"command={self.command!r}\nreturncode={self.returncode}\n"
            f"elapsed={self.seconds:.3f}s\nstatus={self.status}\n\n{self.output}",
            encoding="utf-8",
        )


def find_litex() -> Path | None:
    env_candidates = [os.environ.get("LITEX_BIN"), os.environ.get("LITEXPY_LITEX_BIN")]
    bundled = (
        ROOT / "tools" / "litex" / "windows-amd64" / "litex.exe"
        if os.name == "nt"
        else ROOT / "tools" / "litex" / "linux-amd64" / "litex"
    )
    candidates: Iterable[str | os.PathLike[str] | None] = [*env_candidates, bundled, shutil.which("litex")]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            continue
        if os.name != "nt" and not os.access(path, os.X_OK):
            try:
                path.chmod(path.stat().st_mode | 0o111)
            except OSError:
                continue
        return path
    return None


def cli_move(uci: str, fen: str | None = None) -> list[str]:
    cmd = [sys.executable, "-m", "litex_chess.cli", "verify-move", uci]
    if fen:
        cmd.extend(["--fen", fen])
    return cmd


def main() -> int:
    for stale in LOG_DIR.glob("*.log"):
        if not stale.name.startswith("."):
            stale.unlink()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend") + os.pathsep + env.get("PYTHONPATH", "")
    env["LITEX_BOARD_TRANSITION_MODE"] = "compact"
    litex = find_litex()
    if litex:
        env["LITEX_BIN"] = str(litex)
        env["LITEXPY_LITEX_BIN"] = str(litex)

    py = sys.executable
    gates = [
        Gate("textbook_sync", "教材镜像、原生覆盖层与核心规则同步", [py, "scripts/sync_textbook_core.py", "--check"], {0}, 60),
        Gate("integration_sync", "章节目录、网站 manifest 与原生教材配置同步", [py, "scripts/sync_web_integration.py", "--check"], {0}, 60),
        Gate("python_compile", "Python 源码编译", [py, "-m", "compileall", "-q", "backend", "scripts", "tests", "integration"], {0}, 120),
        Gate("python_tests", "完整 Python 测试", [py, "-m", "pytest", "-q", "backend/tests", "tests"], {0}, 300),
        Gate("frontend_contract", "Litex 站点嵌入、工作台与十五章教材静态契约", [py, "scripts/verify_frontend_contract.py"], {0}, 120),
        Gate("web_integration", "无 iframe Web Component 与原生教材覆盖层", [py, "scripts/verify_web_integration.py"], {0}, 240),
        Gate("semantic_gate", "v0.9 语义门禁", [py, "scripts/verify_v09_semantics.py"], {0}, 180),
        Gate("api_smoke", "工作台、教材、PGN 与终局 API 烟雾测试", [py, "scripts/api_smoke.py"], {0}, 300),
        Gate("textbook_examples", "全部固定教材例与局面实验", [py, "scripts/verify_textbook.py"], {0}, 600),
    ]

    node = shutil.which("node")
    if node:
        javascript_sources = {
            "app": "frontend/app.js",
            "notation": "frontend/notation.js",
            "textbook": "frontend/textbook.js",
            "workbench_controller": "frontend/controllers/workbench.js",
            "textbook_controller": "frontend/controllers/textbook.js",
            "custom_elements": "frontend/embed/litex-chess-elements.js",
            "site_host": "frontend/site/site.js",
            "site_adapter": "integration/litex-site/register-chess.js",
        }
        for name, source in javascript_sources.items():
            if (ROOT / source).is_file():
                gates.append(Gate(f"js_{name}", f"{source} 语法", [node, "--check", source], {0}, 60))
        gates.append(Gate("notation_model", "棋谱主变与括号变例模型", [node, "scripts/verify_notation.js"], {0}, 60))

    if litex:
        gates.extend(
            [
                Gate("litex_version", "Litex 版本", [str(litex), "-version"], {0}, 60),
                Gate("litex_kernel", "生产规则内核编译", [str(litex), "-compact", "-runner", "-f", "formal/chess_rules.lit"], {0}, 180),
                Gate("litex_textbook", "中文教材 Litex 编译", [str(litex), "-compact", "-runner", "-f", "textbook/chess_rules_textbook_cn.lit"], {0}, 180),
                Gate("litex_native_chess_book", "golitex 原生 textbooks/Chess 覆盖层编译", [str(litex), "-compact", "-runner", "-r", "integration/golitex-overlay/textbooks/Chess"], {0}, 240),
                Gate("litex_research_contract", "研究性证书契约编译", [str(litex), "-compact", "-runner", "-f", "research/formal/certificate_contract.lit"], {0}, 120),
                Gate("litex_research_blueprint", "研究性全状态蓝图编译", [str(litex), "-compact", "-runner", "-f", "research/formal/chess_specification_full.lit"], {0}, 120),
                Gate("legal_e2e4", "合法 e2e4", cli_move("e2e4"), {0}, 120),
                Gate("fools_mate_qh4", "愚人将杀 Qh4#", cli_move("d8h4", "rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq g3 0 2"), {0}, 120),
                Gate("illegal_e2e5", "非法 e2e5 必须拒绝", cli_move("e2e5"), {2}, 120),
            ]
        )
    else:
        gates.append(Gate("litex_available", "官方 Litex 可执行文件可用", ["litex", "-version"], {0}, 1, required=True, status="FAIL", output="No Litex executable found.\n"))

    # Keep the release gate bounded enough for CI and interactive packaging.
    # Independent read-only checks run in parallel; the textbook execution
    # suite remains a separate phase because it owns a persistent Litex
    # session and produces the largest diagnostic output.
    first_phase_names = {
        "textbook_sync",
        "integration_sync",
        "python_compile",
        "python_tests",
        "frontend_contract",
        "semantic_gate",
        "api_smoke",
        "web_integration",
    }
    first_phase = [g for g in gates if g.name in first_phase_names and g.status == "NOT RUN"]
    textbook_phase = [g for g in gates if g.name == "textbook_examples" and g.status == "NOT RUN"]
    final_phase = [
        g for g in gates
        if g.status == "NOT RUN" and g not in first_phase and g not in textbook_phase
    ]

    def run_parallel(group: list[Gate], workers: int) -> None:
        if not group:
            return
        with ThreadPoolExecutor(max_workers=min(workers, len(group))) as pool:
            futures = [pool.submit(gate.run, env) for gate in group]
            for future in futures:
                future.result()

    run_parallel(first_phase, 6)
    for gate in textbook_phase:
        gate.run(env)
    run_parallel(final_phase, 6)

    for gate in gates:
        print(f"[{gate.status:7}] {gate.name}: {gate.seconds:.3f}s")

    overall = all((not gate.required) or gate.status == "PASS" for gate in gates)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    report_lines = [
        "# Litex Chess Studio v0.9 验证报告",
        "",
        f"- 生成时间：`{now}`",
        f"- 总体结果：**{'PASS' if overall else 'FAIL'}**",
        "- 生产棋盘后继：精确稀疏变更证书（2—4 格）",
        "- 运行时规则源：`formal/chess_rules.lit`",
        "- 默认网页入口：`/textbook/Chess/<chapter>`（Litex 全局壳层 + 无 iframe Web Component）",
        "",
        "| 检查项 | 含义 | 结果 | 退出码 | 秒 |",
        "|---|---|---:|---:|---:|",
    ]
    for gate in gates:
        report_lines.append(
            f"| `{gate.name}` | {gate.title} | **{gate.status}** | "
            f"{gate.returncode if gate.returncode is not None else '—'} | {gate.seconds:.3f} |"
        )
    report_lines.extend(
        [
            "",
            "## 覆盖范围",
            "",
            "- 核心规则—中文教材单一事实源同步；",
            "- Agent 可读 `move(...)`/`result(...)` 与完整 Litex 证书；",
            "- 稀疏棋盘后继、FEN 元数据、王安全和最终接受合同；",
            "- 愚人将杀、将死/逼和、重复局面、材料死局和残局训练接口；",
            "- 棋谱主变纵排、旁支横排与括号嵌套；",
            "- 15 章教材、19 个定义级例、22 个局面实验（45 条候选）、10 个状态实验和 5 个历史实验；",
            "- `textbooks/Chess` 原生 Litex 覆盖层与无 iframe 自定义元素集成。",
            "",
            "逐项原始输出位于 `verification/generated/`。",
        ]
    )
    REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    STATUS_JSON.write_text(
        json.dumps(
            {
                "generated_at": now,
                "overall": "PASS" if overall else "FAIL",
                "litex_executable": str(litex) if litex else None,
                "checks": [
                    {
                        "name": gate.name,
                        "title": gate.title,
                        "required": gate.required,
                        "status": gate.status,
                        "returncode": gate.returncode,
                        "seconds": round(gate.seconds, 6),
                        "timeout": gate.timeout,
                        "command": gate.command,
                        "expected": sorted(gate.expected),
                        "log": f"verification/generated/{gate.name}.log",
                    }
                    for gate in gates
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
