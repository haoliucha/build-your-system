#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")/../hooks/scripts" && pwd)"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
export CLAUDE_DESKTOP_SUPPORT_DIR="$TMP_DIR"
export CLAUDE_DESKTOP_LOG="$TMP_DIR/main.log"

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

# ---- desktop_session_state / desktop_session_focus_ts ----

write_session local_state_a 5000 false
write_session local_state_z 6000 true
assert_eq "$(desktop_session_state local_state_a)" "active"
assert_eq "$(desktop_session_state local_state_z)" "archived"
assert_eq "$(desktop_session_state local_nope)" "missing"
assert_eq "$(desktop_session_state '')" "missing"
echo "PASS: session state active/archived/missing"

assert_eq "$(desktop_session_focus_ts local_state_a)" "5000"
assert_eq "$(desktop_session_focus_ts local_nope)" ""
echo "PASS: session focus timestamp"

# ---- desktop_supported_route_live (GrowthBook fcache) ----

write_fcache() {  # $1 = raw json for the 4217215889 feature, or "" to omit it
    /usr/bin/python3 - "$TMP_DIR" "$1" <<'PYF'
import gzip, json, os, sys
feature = json.loads(sys.argv[2]) if sys.argv[2] else None
features = {"4217215889": feature} if feature is not None else {"999": {"on": True}}
blob = gzip.compress(json.dumps({"timestamp": 1, "mode": "1p", "features": features}).encode())
with open(os.path.join(sys.argv[1], "fcache"), "wb") as fh:
    fh.write(bytes([67, 76, 70, 2, 0, 154, 183, 226]) + blob)
PYF
}

desktop_supported_route_live && { echo "FAIL: missing fcache should mean gate off"; exit 1; }
echo "PASS: missing fcache → supported route not live"

write_fcache '{"on": true, "value": true}'
desktop_supported_route_live || { echo "FAIL: on:true should mean live"; exit 1; }
echo "PASS: gate on → supported route live"

write_fcache '{"on": false, "off": true}'
desktop_supported_route_live && { echo "FAIL: on:false should mean not live"; exit 1; }
echo "PASS: gate off → supported route not live"

write_fcache ""
desktop_supported_route_live && { echo "FAIL: absent gate key should mean not live"; exit 1; }
echo "PASS: gate key absent → supported route not live"

printf 'GARBAGE not the magic' > "$TMP_DIR/fcache"
desktop_supported_route_live && { echo "FAIL: bad magic should mean not live"; exit 1; }
echo "PASS: unrecognised fcache format → falls back to the ungated route"

# ---- desktop_wait_for_focus ----

rm -f "$SESSIONS"/local_*.json
write_session local_w_target 1000 false
write_session local_w_other  9000 false

# mode=max: target is not on top → must time out
desktop_wait_for_focus local_w_target 0.4 max "" && { echo "FAIL: max should time out"; exit 1; }
echo "PASS: wait(max) times out while another session is on top"

write_session local_w_target 9999 false
desktop_wait_for_focus local_w_target 0.4 max "" || { echo "FAIL: max should succeed"; exit 1; }
echo "PASS: wait(max) succeeds once the target is newest"

# mode=advance: the target's OWN stamp must move past the pre-fire value.
# This is the cold-app case — a stale on-disk stamp must NOT count as a landing.
desktop_wait_for_focus local_w_target 0.4 advance 9999 && { echo "FAIL: advance must not accept an unchanged stamp"; exit 1; }
echo "PASS: wait(advance) rejects a stale stamp (no false success on a quit app)"

desktop_wait_for_focus local_w_target 0.4 advance 5000 || { echo "FAIL: advance should accept a newer stamp"; exit 1; }
echo "PASS: wait(advance) accepts an advanced stamp"

# an archived target can never satisfy mode=max — the caller must short-circuit
write_session local_w_arch 99999 true
desktop_wait_for_focus local_w_arch 0.4 max "" && { echo "FAIL: archived must never satisfy max"; exit 1; }
echo "PASS: archived target never satisfies wait(max)"

# ---- desktop_log_hint ----

printf '%s\n' "2026-09-04 10:00:00 [info] old line before the offset" > "$CLAUDE_DESKTOP_LOG"
offset=$(wc -c < "$CLAUDE_DESKTOP_LOG" | tr -d ' ')
assert_eq "$(desktop_log_hint "$offset")" ""
echo "PASS: log hint is empty when the app said nothing new"

printf '%s\n' "2026-09-04 10:00:01 [info] noise"               "2026-09-04 10:00:02 [info] claudeURLHandler: code entry deep link gated off" >> "$CLAUDE_DESKTOP_LOG"
assert_eq "$(desktop_log_hint "$offset")" " — app said: claudeURLHandler: code entry deep link gated off"
echo "PASS: log hint reads only lines appended after the offset"

# a bracket inside a logged object must not truncate the message
printf '%s\n' '2026-09-04 10:00:03 [warn] claudeURLHandler: failed {ids: [1] } tail' >> "$CLAUDE_DESKTOP_LOG"
assert_eq "$(desktop_log_hint "$offset")" " — app said: claudeURLHandler: failed {ids: [1] } tail"
echo "PASS: log hint keeps brackets inside logged objects"

echo "ALL TESTS PASS"
