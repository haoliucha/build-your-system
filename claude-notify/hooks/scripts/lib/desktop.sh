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

# Return 0 when the desktop app's main process is running.
# Matches the main binary only; the Helper processes live under Contents/Frameworks.
# `ps` rather than `pgrep`: pgrep does not match this app by name or full path here
# (verified), while the ps scan does.
desktop_app_running() {
    ps -axo command= 2>/dev/null \
        | grep -q '^/Applications/Claude\.app/Contents/MacOS/Claude'
}

# Echo "active" | "archived" | "missing" for a session id.
# Archived sessions are excluded from desktop_focused_session_id by design, so a
# jump to one can never be confirmed — the caller needs to know that up front.
desktop_session_state() {
    /usr/bin/python3 - "$CLAUDE_DESKTOP_SUPPORT_DIR" "$1" <<'PY' 2>/dev/null || echo missing
import glob, json, os, sys

target = sys.argv[2]
for path in glob.glob(os.path.join(sys.argv[1], "claude-code-sessions", "*", "*", "local_*.json")):
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        continue
    if isinstance(data, dict) and data.get("sessionId") == target:
        print("archived" if data.get("isArchived") else "active")
        break
else:
    print("missing")
PY
}

# Echo one session's own lastFocusedAt (epoch ms), or "" if unknown.
desktop_session_focus_ts() {
    /usr/bin/python3 - "$CLAUDE_DESKTOP_SUPPORT_DIR" "$1" <<'PY' 2>/dev/null
import glob, json, os, sys

target = sys.argv[2]
for path in glob.glob(os.path.join(sys.argv[1], "claude-code-sessions", "*", "*", "local_*.json")):
    try:
        with open(path) as fh:
            data = json.load(fh)
    except Exception:
        continue
    if isinstance(data, dict) and data.get("sessionId") == target:
        at = data.get("lastFocusedAt")
        print(int(at) if isinstance(at, (int, float)) else "")
        break
PY
}

# Return 0 when the app's OWN supported deep link (claude://code/continue) is live.
#
# That link sits behind GrowthBook gate 4217215889. The evaluated feature map is
# cached at <support>/fcache: 8-byte magic + gzipped JSON {timestamp, mode, features}.
# Reading it lets us fire exactly ONE url per jump — the supported one when it works,
# our internal-route equivalent otherwise — instead of firing both and hoping. That
# matters: app.on("open-url") stashes a pending url in a SINGLE slot while the window
# is still booting, so a second url does not add a chance, it destroys the first one.
#
# Unreadable / unknown format -> treat as off, i.e. keep using the ungated route that
# works today.
desktop_supported_route_live() {
    local state
    state=$(/usr/bin/python3 - "$CLAUDE_DESKTOP_SUPPORT_DIR" <<'PY' 2>/dev/null
import gzip, json, os, sys

MAGIC = bytes([67, 76, 70, 2, 0, 154, 183, 226])
try:
    with open(os.path.join(sys.argv[1], "fcache"), "rb") as fh:
        blob = fh.read()
    if not blob.startswith(MAGIC):
        raise ValueError("unexpected fcache magic")
    feature = (json.loads(gzip.decompress(blob[8:])).get("features") or {}).get("4217215889") or {}
    print("on" if feature.get("on") else "off")
except Exception:
    print("unknown")
PY
)
    [ "$state" = "on" ]
}

# Block until the app confirms the jump landed, or the budget runs out.
#   $1 session id   $2 timeout seconds   $3 mode: max|advance   $4 pre-fire timestamp
#
# mode=max      the target must become the newest focus-stamped session (app was
#               already running, and it was NOT already the newest)
# mode=advance  the target's OWN stamp must move past $4 (app was cold — a boot
#               re-stamps on mount, and the on-disk stamp survives a quit, so a
#               plain max comparison would match instantly and prove nothing)
desktop_wait_for_focus() {
    /usr/bin/python3 - "$CLAUDE_DESKTOP_SUPPORT_DIR" "$1" "$2" "$3" "$4" <<'PY' 2>/dev/null
import glob, json, os, sys, time

support, target, timeout, mode, pre = sys.argv[1:6]
pattern = os.path.join(support, "claude-code-sessions", "*", "*", "local_*.json")
pre_ts = int(pre) if pre.strip().isdigit() else -1
deadline = time.time() + float(timeout)

def scan():
    best_at, best_id, mine = -1, "", None
    for path in glob.glob(pattern):
        try:
            with open(path) as fh:
                data = json.load(fh)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        at = data.get("lastFocusedAt")
        at = at if isinstance(at, (int, float)) else None
        if data.get("sessionId") == target and at is not None:
            mine = at
        if data.get("isArchived") or at is None:
            continue
        if at > best_at:
            best_at, best_id = at, data.get("sessionId") or ""
    return best_id, mine

while True:
    top, mine = scan()
    if mode == "advance":
        if mine is not None and mine > pre_ts:
            sys.exit(0)
    elif top == target:
        sys.exit(0)
    if time.time() >= deadline:
        sys.exit(1)
    time.sleep(0.25)
PY
}

CLAUDE_DESKTOP_LOG="${CLAUDE_DESKTOP_LOG:-$HOME/Library/Logs/Claude/main.log}"

# Echo " — app said: <last claudeURLHandler message>" for lines the app appended
# after byte offset $1, else nothing.
# Reading from a captured offset rather than tailing N lines keeps the hint about
# THIS jump: the app writes hundreds of unrelated lines a minute, so a fixed tail
# window almost never contains the relevant line.
desktop_log_hint() {
    local line
    line=$(tail -c "+$(( ${1:-0} + 1 ))" "$CLAUDE_DESKTOP_LOG" 2>/dev/null \
        | grep 'claudeURLHandler' | tail -1)
    [ -n "$line" ] || return 0
    # single # — a greedy ##*"] " would also eat brackets inside logged objects
    printf ' — app said: %s' "${line#*] }"
}
