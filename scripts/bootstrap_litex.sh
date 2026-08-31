#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/litex.lock"
SOURCE_DIR="${LITEX_SOURCE_DIR:-$ROOT/.local/src/golitex}"
BIN_DIR="${LITEX_BIN_DIR:-$ROOT/.local/bin}"
mkdir -p "$(dirname "$SOURCE_DIR")" "$BIN_DIR"

repo="$(sed -n 's/^repository = "\([^"]*\)"/\1/p' "$LOCK")"
commit="$(sed -n 's/^commit = "\([^"]*\)"/\1/p' "$LOCK")"
if [[ -z "$repo" ]]; then
  echo "litex.lock does not contain repository" >&2
  exit 2
fi

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  git clone "$repo" "$SOURCE_DIR"
else
  git -C "$SOURCE_DIR" remote set-url origin "$repo"
  git -C "$SOURCE_DIR" fetch origin --tags --prune
fi

if [[ -z "$commit" || "$commit" == "unknown" ]]; then
  commit="$(git -C "$SOURCE_DIR" rev-parse origin/main)"
  echo "WARNING: lock commit was unknown; using current origin/main $commit" >&2
fi

git -C "$SOURCE_DIR" checkout --detach "$commit"
cargo build --release --manifest-path "$SOURCE_DIR/Cargo.toml" --bin litex
cp "$SOURCE_DIR/target/release/litex" "$BIN_DIR/litex"
chmod +x "$BIN_DIR/litex"

printf 'Built Litex at %s\n' "$BIN_DIR/litex"
"$BIN_DIR/litex" -version || true
printf '\nUse it in the current shell with:\n'
printf '  export LITEX_BIN=%q\n' "$BIN_DIR/litex"
printf '  export LITEXPY_LITEX_BIN=%q\n' "$BIN_DIR/litex"
