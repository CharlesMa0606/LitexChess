# Litex Chess 网站嵌入开发包

本包面向把国际象棋教材与工作台接入 Litex Textbooks 网站的开发者。它不包含平台相关的 Litex 二进制；请使用宿主已有的 Litex，或运行 `scripts/bootstrap_litex.sh` 按 `litex.lock` 构建。

## 最短接入路径

1. `python integration/install_into_golitex.py /path/to/golitex`：安装原生 `textbooks/Chess`。
2. `python integration/install_web_assets.py /path/to/site/public`：发布 `/extensions/chess/` 静态资源。
3. 在宿主网站加载 `embed/litex-chess-elements.js`，并用 `integration/litex-site/register-chess.js` 注册章节与工作台路由。
4. 同域提供 `/api/` 与 `/textbook-source/`，或者通过元素属性指定其他基址。
5. 按 `integration/litex-site/HOST_INTEGRATION_CONTRACT_CN.md` 检查：无 iframe、单一全局壳层、同一 Litex 门禁、章节和 FEN 可深链。

## 本地集成预览

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
bash scripts/bootstrap_litex.sh
export LITEX_BIN="$PWD/.local/bin/litex"
export LITEXPY_LITEX_BIN="$LITEX_BIN"
bash scripts/run_dev.sh
```

访问 `/textbook/Chess/position-state`；独立兼容页仅用于调试。
