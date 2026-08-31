#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -d "$ROOT/.venv" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi
if [[ -x "$ROOT/.local/bin/litex" ]]; then
  LITEX="$ROOT/.local/bin/litex"
elif [[ -f "$ROOT/tools/litex/linux-amd64/litex" ]]; then
  chmod +x "$ROOT/tools/litex/linux-amd64/litex" 2>/dev/null || true
  LITEX="$ROOT/tools/litex/linux-amd64/litex"
elif command -v litex >/dev/null 2>&1; then
  LITEX="$(command -v litex)"
else
  echo "Litex executable not found. Run scripts/bootstrap_litex.sh." >&2
  exit 2
fi
export LITEX_BIN="$LITEX"
export LITEXPY_LITEX_BIN="$LITEX"
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn litex_chess.api:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --reload
