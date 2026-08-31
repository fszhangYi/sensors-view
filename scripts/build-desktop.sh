#!/usr/bin/env bash
# Desktop packaging entry for sensors-view.
#   Linux host → Linux onedir:  scheme-a-linux-to-linux-desktop
#   Linux host → Windows onedir: scheme-a-linux-to-windows-desktop
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEARCH="${WINEARCH:-win64}"
export WINEPREFIX="${WINEPREFIX:-$ROOT/.wine-sensors-view}"

TARGET="native"
SKIP_FRONTEND=1
EXTRA=()

usage() {
  cat <<'EOF'
Usage: bash scripts/build-desktop.sh [options]

Build a self-contained desktop onedir under release/.

Options:
  --target native|linux|windows   Build target (default: native = Linux)
  --skip-frontend                 Skip frontend build (default)
  --with-frontend                 Reserved if a Vite frontend is added later
  -h, --help                      Show this help

Environment:
  PIP_INDEX_URL   pip mirror (default: Tsinghua)
  WINEPREFIX      Wine prefix for --target windows (default: .wine-sensors-view)
  WINEARCH        win64

Examples:
  ./build.sh                      # Linux x64 package
  ./build.sh --target windows     # Windows x64 via Wine
  bash scripts/build-desktop.sh --target native

Output (native/linux):
  release/sensors-view-desktop-linux-x64-<UTC>/
  release/sensors-view-desktop-linux-x64-<UTC>.tar.gz
  release/sensors-view-desktop-linux-x64-<UTC>.zip

Output (windows):
  release/sensors-view-desktop-windows-x64-<UTC>/
  release/sensors-view-desktop-windows-x64-<UTC>.zip

Prerequisites:
  native/linux: python3, venv, curl (PyInstaller installed into .tools/linux-venv)
  windows:      wine64 (or wine), curl, unzip, python3
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --skip-frontend)
      SKIP_FRONTEND=1
      shift
      ;;
    --with-frontend)
      SKIP_FRONTEND=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      EXTRA+=("$1")
      shift
      ;;
  esac
done

if [[ "$TARGET" == "linux" ]]; then
  TARGET="native"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
fi

if [[ "$TARGET" == "windows" ]]; then
  if ! command -v wine64 >/dev/null 2>&1 && ! command -v wine >/dev/null 2>&1; then
    echo "error: wine64/wine not found — install Wine (win64) first" >&2
    exit 1
  fi
fi

ARGS=(--target "$TARGET")
if [[ "$SKIP_FRONTEND" -eq 1 ]]; then
  ARGS+=(--skip-frontend)
fi
if [[ ${#EXTRA[@]} -gt 0 ]]; then
  ARGS+=("${EXTRA[@]}")
fi

echo "==> sensors-view desktop build"
echo "    root:      $ROOT"
echo "    target:    $TARGET"
echo "    pip index: $PIP_INDEX_URL"
if [[ "$TARGET" == "windows" ]]; then
  echo "    wineprefix:$WINEPREFIX"
fi
echo

exec python3 "$ROOT/scripts/build_desktop.py" "${ARGS[@]}"
