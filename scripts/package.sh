#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(dirname "$ROOT")"
NAME="$(basename "$ROOT")"
OUT_DIR="${1:-$PARENT}"
mkdir -p "$OUT_DIR"
ZIP="$OUT_DIR/${NAME}.zip"
TAR="$OUT_DIR/${NAME}.tar.gz"
CHECKSUMS="$OUT_DIR/${NAME}_SHA256SUMS.txt"

rm -f "$ZIP" "$TAR" "$CHECKSUMS" "$ZIP.sha256" "$TAR.sha256"

# Freeze the exact packaged file set after the release gate has written its
# report and logs.  The manifest excludes only itself and disposable caches.
python3 "$ROOT/scripts/generate_manifest.py"

cd "$PARENT"
zip -qr "$ZIP" "$NAME" \
  -x "$NAME/.local/*" \
     "$NAME/.venv/*" \
     "$NAME/**/__pycache__/*" \
     "$NAME/.pytest_cache/*" \
     "$NAME/**/*.pyc"

tar -czf "$TAR" \
  --exclude="$NAME/.local" \
  --exclude="$NAME/.venv" \
  --exclude="$NAME/.pytest_cache" \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "$NAME"

sha256sum "$ZIP" "$TAR" > "$CHECKSUMS"
sha256sum "$ZIP" > "$ZIP.sha256"
sha256sum "$TAR" > "$TAR.sha256"

unzip -tq "$ZIP" >/dev/null
tar -tzf "$TAR" >/dev/null

printf '%s\n%s\n%s\n' "$ZIP" "$TAR" "$CHECKSUMS"
