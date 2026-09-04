#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")/../hooks/scripts" && pwd)"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
export CLAUDE_DESKTOP_SUPPORT_DIR="$TMP_DIR"

source "$SCRIPT_DIR/lib/desktop.sh"

assert_eq() { [ "$1" = "$2" ] || { echo "FAIL: expected '$2', got '$1'"; exit 1; }; }

SESSIONS="$TMP_DIR/claude-code-sessions/acct/device"
mkdir -p "$SESSIONS"

write_session() {  # id, lastFocusedAt, isArchived
    cat > "$SESSIONS/$1.json" <<JSON
{"sessionId": "$1", "lastFocusedAt": $2, "isArchived": $3, "title": "t"}
JSON
}

set_levels() {  # raw json for notificationLevels, or "" to omit the key
    if [ -z "$1" ]; then
        echo '{"darkMode": true}' > "$TMP_DIR/config.json"
    else
        echo "{\"notificationLevels\": $1}" > "$TMP_DIR/config.json"
    fi
}

# ---- desktop_valid_session_id ----

desktop_valid_session_id "local_52ea6481-9bd9-4a4d-a179-b8bd1f055f43" \
    || { echo "FAIL: rejected a well-formed id"; exit 1; }
echo "PASS: accepts a well-formed session id"

for bad in "" "not-a-local-id" "local_" "session_abc" "local_abc def" \
           'local_x"; rm -rf /' 'local_$(whoami)' "local_a/../b" \
           "local_$(printf 'a%.0s' {1..65})"; do
    if desktop_valid_session_id "$bad"; then
        echo "FAIL: accepted '$bad'"; exit 1
    fi
done
echo "PASS: rejects empty, malformed, over-long and injection-shaped ids"

# 64 chars after the prefix is the documented upper bound
desktop_valid_session_id "local_$(printf 'a%.0s' {1..64})" \
    || { echo "FAIL: rejected a 64-char id"; exit 1; }
echo "PASS: accepts the 64-char upper bound"

# ---- desktop_focused_session_id ----

assert_eq "$(desktop_focused_session_id)" ""
echo "PASS: empty store → no focused session"

write_session local_aaa 1000 false
write_session local_bbb 3000 false
write_session local_ccc 2000 false
assert_eq "$(desktop_focused_session_id)" "local_bbb"
echo "PASS: newest lastFocusedAt wins"

# an archived session focused most recently must not win
write_session local_ddd 9000 true
assert_eq "$(desktop_focused_session_id)" "local_bbb"
echo "PASS: archived sessions are ignored"

# a corrupt file must not take down the scan
echo 'not json {{{' > "$SESSIONS/local_eee.json"
assert_eq "$(desktop_focused_session_id)" "local_bbb"
echo "PASS: unparseable session files are skipped"

# a session that has never been focused carries no lastFocusedAt
cat > "$SESSIONS/local_fff.json" <<'JSON'
{"sessionId": "local_fff", "isArchived": false}
JSON
assert_eq "$(desktop_focused_session_id)" "local_bbb"
echo "PASS: sessions without lastFocusedAt are ignored"

# ---- desktop_native_banner_on ----

# no config.json at all → assume the app is notifying, so we stay silent
desktop_native_banner_on idle || { echo "FAIL: missing config should mean banner on"; exit 1; }
echo "PASS: missing config.json → native banner assumed on"

set_levels ""
desktop_native_banner_on idle || { echo "FAIL: absent notificationLevels should mean banner on"; exit 1; }
echo "PASS: absent notificationLevels → native banner on"

set_levels '{"permission": "off"}'
desktop_native_banner_on idle || { echo "FAIL: absent idle key should mean banner on"; exit 1; }
echo "PASS: absent category key → native banner on"

set_levels '{"idle": "banner", "permission": "off", "question": "badge"}'
desktop_native_banner_on idle || { echo "FAIL: 'banner' should mean banner on"; exit 1; }
echo "PASS: level 'banner' → native banner on"

desktop_native_banner_on permission && { echo "FAIL: 'off' should mean banner off"; exit 1; }
echo "PASS: level 'off' → native banner off"

desktop_native_banner_on question && { echo "FAIL: 'badge' should mean banner off"; exit 1; }
echo "PASS: level 'badge' → native banner off (badge only, no banner)"

echo 'not json {{{' > "$TMP_DIR/config.json"
desktop_native_banner_on idle || { echo "FAIL: unparseable config should mean banner on"; exit 1; }
echo "PASS: unparseable config.json → native banner assumed on"

echo "ALL TESTS PASS"
