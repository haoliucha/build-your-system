#!/bin/bash
set -euo pipefail

EXPECTED_LEGACY="$HOME/.agents/skills/x-unfollow"
EXPECTED_BACKUP_ROOT="$HOME/.agents/skills-disabled"
LEGACY_SKILL="${X_PLUGIN_LEGACY_SKILL_DIR:-$EXPECTED_LEGACY}"
BACKUP_ROOT="${X_PLUGIN_LEGACY_BACKUP_ROOT:-$EXPECTED_BACKUP_ROOT}"
STAMP="${X_PLUGIN_MIGRATION_STAMP:-$(date +%Y%m%d-%H%M%S)}"
TARGET="$BACKUP_ROOT/x-unfollow-legacy-$STAMP"
DRY_RUN=0
TEST_MODE="${X_PLUGIN_MIGRATION_TEST_MODE:-0}"

if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
elif [ "$#" -ne 0 ]; then
  echo "usage: migrate-legacy-skill.sh [--dry-run]" >&2
  exit 2
fi

case "$STAMP" in
  ''|*[!A-Za-z0-9._-]*) echo "REFUSED: migration stamp must be one safe path segment" >&2; exit 2 ;;
esac
if [ "$TEST_MODE" != "1" ] && { [ "$LEGACY_SKILL" != "$EXPECTED_LEGACY" ] || [ "$BACKUP_ROOT" != "$EXPECTED_BACKUP_ROOT" ]; }; then
  echo "REFUSED: production migration only accepts $EXPECTED_LEGACY -> $EXPECTED_BACKUP_ROOT" >&2
  exit 2
fi
if [ ! -e "$LEGACY_SKILL" ]; then
  echo "legacy x-unfollow is already absent: $LEGACY_SKILL"
  exit 0
fi
if [ -L "$LEGACY_SKILL" ] || [ ! -d "$LEGACY_SKILL" ] || [ ! -f "$LEGACY_SKILL/SKILL.md" ]; then
  echo "REFUSED: expected a real standalone skill directory at $LEGACY_SKILL" >&2
  exit 2
fi
if ! /usr/bin/grep -q '^name: x-unfollow$' "$LEGACY_SKILL/SKILL.md"; then
  echo "REFUSED: $LEGACY_SKILL/SKILL.md does not identify x-unfollow" >&2
  exit 2
fi
if [ -L "$BACKUP_ROOT" ]; then
  echo "REFUSED: backup root must not be a symlink: $BACKUP_ROOT" >&2
  exit 2
fi
if [ -e "$TARGET" ]; then
  echo "REFUSED: backup target already exists: $TARGET" >&2
  exit 2
fi

LEGACY_SKILL="$LEGACY_SKILL" BACKUP_ROOT="$BACKUP_ROOT" TARGET="$TARGET" /usr/bin/python3 <<'PY'
import os

source = os.path.realpath(os.environ["LEGACY_SKILL"])
backup = os.path.realpath(os.environ["BACKUP_ROOT"])
target = os.path.realpath(os.environ["TARGET"])

def contains(parent, child):
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False

if source == backup or contains(source, backup) or contains(backup, source):
    raise SystemExit(f"REFUSED: source and backup root overlap: {source} <-> {backup}")
if not contains(backup, target) or target == backup:
    raise SystemExit(f"REFUSED: target escapes backup root: {target}")
if source == target or contains(source, target) or contains(target, source):
    raise SystemExit(f"REFUSED: source and target overlap: {source} <-> {target}")
PY

echo "legacy=$LEGACY_SKILL"
echo "backup=$TARGET"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run: no files moved"
  exit 0
fi

/bin/mkdir -p "$BACKUP_ROOT"
/bin/mv "$LEGACY_SKILL" "$TARGET"
echo "migrated: legacy skill is no longer discoverable; backup is recoverable at $TARGET"
