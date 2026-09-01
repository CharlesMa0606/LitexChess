#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
PY=${PYTHON:-${PY:-/opt/pyvenv/bin/python}}
[ -x "$PY" ] || PY=python3
exec "$PY" scripts/verify_release.py
