#!/usr/bin/env bash
# Convenience entry: desktop packaging (default Linux native).
#   ./build.sh                 → Linux onedir
#   ./build.sh --target windows → Windows onedir via Wine
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/build-desktop.sh" "$@"
