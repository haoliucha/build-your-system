#!/bin/bash
# Claude desktop app (Code tab) helpers.
#
# The desktop app keeps one JSON file per Code session under
#   ~/Library/Application Support/Claude/claude-code-sessions/<a>/<b>/local_<uuid>.json
# and its own settings in that directory's config.json. Both are private
# formats, so every read here degrades to a safe default instead of failing:
# an unreadable store means "not focused" (notify anyway) and an unreadable
# config means "the app's own banner is on" (stay silent rather than
# double-notify).

CLAUDE_DESKTOP_SUPPORT_DIR="${CLAUDE_DESKTOP_SUPPORT_DIR:-$HOME/Library/Application Support/Claude}"

# Accept only ids the app's own deep-link handler accepts (/^local_[A-Za-z0-9-]{1,64}$/).
# The value reaches jump-to-claude.sh through a world-readable /tmp file and is
# interpolated into a URL passed to `open`, so this is a security boundary, not
# just a sanity check.
desktop_valid_session_id() {
    [[ "$1" =~ ^local_[A-Za-z0-9-]{1,64}$ ]]
}

# Echo the session id the user is currently looking at, or "" if undetermined.
# lastFocusedAt is rewritten within ~1s of a tab switch, so the largest value
# across non-archived sessions is the visible one.
desktop_focused_session_id() {
    /usr/bin/python3 - "$CLAUDE_DESKTOP_SUPPORT_DIR" <<'PY' 2>/dev/null
import glob, json, os, sys

best_at, best_id = -1, ""
pattern = os.path.join(sys.argv[1], "claude-code-sessions", "*", "*", "local_*.json")
for path in glob.glob(pattern):
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        continue
    if not isinstance(data, dict) or data.get("isArchived"):
        continue
    at = data.get("lastFocusedAt") or 0
    if isinstance(at, (int, float)) and at > best_at:
        best_at, best_id = at, data.get("sessionId") or ""
print(best_id)
PY
}

# Return 0 when the desktop app will post its own banner for this category.
# notificationLevels maps off/badge -> no banner, banner -> banner; an unset
# level also means banner (verified against the app's own default).
# $1: idle | permission | question
desktop_native_banner_on() {
    local level
    level=$(/usr/bin/python3 - "$CLAUDE_DESKTOP_SUPPORT_DIR" "$1" <<'PY' 2>/dev/null
import json, os, sys

try:
    with open(os.path.join(sys.argv[1], "config.json")) as fh:
        levels = json.load(fh).get("notificationLevels") or {}
    print(levels.get(sys.argv[2]) or "")
except Exception:
    print("")
PY
)
    [ -z "$level" ] || [ "$level" = "banner" ]
}
