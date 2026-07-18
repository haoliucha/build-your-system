#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
BID_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"

case "$#:${1:-}" in
  0:) mode="install" ;;
  1:--uninstall) mode="uninstall" ;;
  *)
    printf 'Usage: %s [--uninstall]\n' "$0" >&2
    exit 2
    ;;
esac

exec python3 "$SCRIPT_DIR/codex-local-lifecycle.py" "$mode" "$BID_ROOT"
