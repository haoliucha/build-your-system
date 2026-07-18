#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
BID_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"
SOURCE_ROOT="$HOME/plugins/bid"
MARKETPLACE_FILE="$HOME/.agents/plugins/marketplace.json"

if [ -L "$MARKETPLACE_FILE" ]; then
  printf 'Conflict: %s is a symlink; refusing to modify it.\n' "$MARKETPLACE_FILE" >&2
  exit 1
fi

if [ ! -e "$SOURCE_ROOT" ] && [ ! -L "$SOURCE_ROOT" ]; then
  mkdir -p "$(dirname -- "$SOURCE_ROOT")"
  ln -s "$BID_ROOT" "$SOURCE_ROOT"
elif [ -L "$SOURCE_ROOT" ]; then
  SOURCE_TARGET="$(CDPATH= cd -- "$SOURCE_ROOT" 2>/dev/null && pwd -P || true)"
  if [ "$SOURCE_TARGET" != "$BID_ROOT" ]; then
    printf 'Conflict: %s is a symlink to a different target.\n' "$SOURCE_ROOT" >&2
    exit 1
  fi
else
  printf 'Conflict: %s exists and is not the expected symlink.\n' "$SOURCE_ROOT" >&2
  exit 1
fi

mkdir -p "$(dirname -- "$MARKETPLACE_FILE")"

MARKETPLACE_FILE="$MARKETPLACE_FILE" python3 - <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path


marketplace_file = Path(os.environ["MARKETPLACE_FILE"])
bid_entry = {
    "name": "bid",
    "source": {"source": "local", "path": "./plugins/bid"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}

if marketplace_file.exists():
    try:
        marketplace = json.loads(marketplace_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Conflict: cannot read {marketplace_file}: {error}", file=sys.stderr)
        raise SystemExit(1)
else:
    marketplace = {
        "name": "local-build-your-system",
        "interface": {"displayName": "Local Build Your System"},
        "plugins": [],
    }

if not isinstance(marketplace, dict):
    print(f"Conflict: {marketplace_file} must contain a JSON object.", file=sys.stderr)
    raise SystemExit(1)

plugins = marketplace.get("plugins")
if not isinstance(plugins, list):
    print(f"Conflict: {marketplace_file} must contain a plugins list.", file=sys.stderr)
    raise SystemExit(1)

existing_bid = [
    plugin
    for plugin in plugins
    if isinstance(plugin, dict) and plugin.get("name") == "bid"
]
if existing_bid:
    if len(existing_bid) == 1 and existing_bid[0] == bid_entry:
        raise SystemExit(0)
    print(f"Conflict: {marketplace_file} contains a different bid entry.", file=sys.stderr)
    raise SystemExit(1)

plugins.append(bid_entry)
temp_fd, temp_name = tempfile.mkstemp(
    prefix=f".{marketplace_file.name}.",
    suffix=".tmp",
    dir=marketplace_file.parent,
)
try:
    with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
        json.dump(marketplace, temp_file, ensure_ascii=False, indent=2)
        temp_file.write("\n")
        temp_file.flush()
        os.fsync(temp_file.fileno())
    os.replace(temp_name, marketplace_file)
except BaseException:
    try:
        os.unlink(temp_name)
    except FileNotFoundError:
        pass
    raise
PY

codex plugin add bid@local-build-your-system

printf 'Source: %s -> %s\n' "$SOURCE_ROOT" "$BID_ROOT"
printf 'Marketplace: %s\n' "$MARKETPLACE_FILE"
printf 'Reminder: start a new Codex task to refresh the skill index.\n'
