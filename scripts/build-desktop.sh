#!/usr/bin/env bash
# Linux → Windows desktop onedir (Wine + embeddable CPython + PyInstaller).
# See: autodl-tmp/office_skills/scheme-a-linux-to-windows-desktop
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEARCH="${WINEARCH:-win64}"
export WINEPREFIX="${WINEPREFIX:-$ROOT/.wine-sensors-view}"

TARGET="windows"
SKIP_FRONTEND=1
EXTRA=()

usage() {
  cat <<'EOF'
Usage: bash scripts/build-desktop.sh [options]

Build a self-contained Windows x64 desktop package under release/.

Options:
  --target windows|native   Build target (default: windows)
  --skip-frontend           Skip frontend build (default, sensors-view is server-rendered)
  --with-frontend           Pass through if a frontend step is added later
  -h, --help                Show this help

Environment:
  PIP_INDEX_URL   pip mirror (default: Tsinghua)
  WINEPREFIX      Wine prefix (default: .wine-sensors-view)
  WINEARCH        win64

Output:
  release/sensors-view-desktop-windows-x64-<UTC>/
  release/sensors-view-desktop-windows-x64-<UTC>.zip

Prerequisites:
  wine64 (or wine), curl, unzip, python3
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

if ! command -v wine64 >/dev/null 2>&1 && ! command -v wine >/dev/null 2>&1; then
  echo "error: wine64/wine not found — install Wine (win64) first" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
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
echo "    wineprefix:$WINEPREFIX"
echo

exec python3 "$ROOT/scripts/build_desktop.py" "${ARGS[@]}"
