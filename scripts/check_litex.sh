#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LITEX="${LITEX_BIN:-${LITEXPY_LITEX_BIN:-}}"
if [[ -z "$LITEX" && -x "$ROOT/.local/bin/litex" ]]; then
  LITEX="$ROOT/.local/bin/litex"
fi
if [[ -z "$LITEX" && -f "$ROOT/tools/litex/linux-amd64/litex" ]]; then
  chmod +x "$ROOT/tools/litex/linux-amd64/litex" 2>/dev/null || true
  LITEX="$ROOT/tools/litex/linux-amd64/litex"
fi
if [[ -z "$LITEX" ]] && command -v litex >/dev/null 2>&1; then
  LITEX="$(command -v litex)"
fi
if [[ -z "$LITEX" || ! -x "$LITEX" ]]; then
  echo "Litex binary not found. Run scripts/bootstrap_litex.sh first." >&2
  exit 2
fi
"$LITEX" -version
"$LITEX" -compact -runner -r "$ROOT/formal"
"$LITEX" -compact -runner -f "$ROOT/textbook/chess_rules_textbook_cn.lit"
