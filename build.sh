#!/usr/bin/env bash
# Convenience entry: Linux → Windows desktop package.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/build-desktop.sh" "$@"
