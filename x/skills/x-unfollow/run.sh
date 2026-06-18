#!/bin/bash
# run.sh — x-unfollow end-to-end orchestrator (follow hygiene).
#
# Pipeline:
#   profile check -> smoke-test -> snapshot /following -> classify -> refresh follower
#   counts (only past-wait accounts) -> re-classify -> [report | unfollow + verify]
#
# Two modes (MODE env):
#   report  (DEFAULT) — produce snapshot + classification + candidate list, then STOP.
#                       NOTHING is unfollowed. This is "筛选/统计/报告".
#   unfollow          — additionally execute unfollows for ELIGIBLE_FOR_UNFOLLOW, then
#                       verify. Use ONLY when the user explicitly asked to 取关/unfollow.
#
# Safety:
#   - unfollow.cjs clicks ONLY the exact target's data-testid$="-unfollow" button, skips
#     accounts that now follow you, never follows/likes/comments/blocks/changes settings.
#   - any anomaly (exit 10-14: CAPTCHA/RATE_LIMIT/LOGIN/RESTRICT/WEBDRIVER) -> HALT + ALERT.txt.
#
# Cross-day note: "days not following back" needs multiple daily snapshots to accrue. On a
# fresh XU_DATA_DIR everyone starts as KEEP_WAITING_GT3 until enough days pass.
#
# Key env:
#   MY_HANDLE=you (required)   MODE=report|unfollow      MIN_DAYS=3   FOLLOWER_THRESHOLD=2000
#   XU_DATA_DIR=~/.config/x-unfollow-data   PROFILE_DIR=~/.config/playwright-chrome-profile-campaign
#   LIMIT=0 (cap unfollows; 0=all)          DRY_RUN=1 (unfollow mode: verify selectors, no click)
#   NODE_PATH must point at a node_modules with playwright (set by caller).

set -o pipefail
export NO_COLOR=1 NODE_DISABLE_COLORS=1 FORCE_COLOR=0
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"

MY_HANDLE="${MY_HANDLE:-}"
MODE="${MODE:-report}"
MIN_DAYS="${MIN_DAYS:-3}"
FOLLOWER_THRESHOLD="${FOLLOWER_THRESHOLD:-2000}"
XU_DATA_DIR="${XU_DATA_DIR:-$HOME/.config/x-unfollow-data}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/.config/playwright-chrome-profile-campaign}"
LIMIT="${LIMIT:-0}"
DATE="${SNAPSHOT_DATE:-$(TZ=Asia/Shanghai date +%F)}"
ALERT="$XU_DATA_DIR/ALERT.txt"
export XU_DATA_DIR PROFILE_DIR ALERT_PATH="$ALERT" SNAPSHOT_DATE="$DATE"

say() { echo "[run $(date +%H:%M:%S)] $*"; }
cleanup_locks() { pkill -9 -f "user-data-dir=$PROFILE_DIR" 2>/dev/null; rm -f "$PROFILE_DIR"/Singleton* 2>/dev/null; sleep 1; }

if [ -z "$MY_HANDLE" ]; then say "FATAL: MY_HANDLE required (your X handle, no @)"; exit 2; fi
if [ "$MODE" != "report" ] && [ "$MODE" != "unfollow" ]; then say "FATAL: MODE must be 'report' or 'unfollow'"; exit 2; fi
mkdir -p "$XU_DATA_DIR/snapshots" "$XU_DATA_DIR/reports"

# ---- Phase 0: profile ------------------------------------------------------
if [ ! -d "$PROFILE_DIR" ]; then
  say "FATAL: profile copy not found: $PROFILE_DIR"
  say "Create it once (while base profile is NOT in use):"
  say "  cp -R ~/.config/playwright-chrome-profile $PROFILE_DIR && rm -f $PROFILE_DIR/Singleton*"
  exit 3
fi
cleanup_locks

# ---- Phase 1: smoke test ---------------------------------------------------
say "smoke-test..."
MY_HANDLE="$MY_HANDLE" PROFILE_DIR="$PROFILE_DIR" node "$SCRIPTS/smoke-test.cjs"
SMOKE=$?
if [ "$SMOKE" -ne 0 ]; then say "smoke-test RED (exit $SMOKE) — refusing to run. Fix env (login/profile)."; exit "$SMOKE"; fi
cleanup_locks

halt_on_anomaly() { # $1 = exit code from a node browser step
  case "$1" in
    10|11|12|13|14) say "!!! ANOMALY (exit $1) — HALT. See $ALERT. Not operating the account further."; exit "$1" ;;
  esac
}

# ---- Phase 2: snapshot /following -----------------------------------------
say "snapshot @$MY_HANDLE /following (date=$DATE)..."
MY_HANDLE="$MY_HANDLE" node "$SCRIPTS/snapshot.cjs"
code=$?; halt_on_anomaly "$code"
if [ "$code" -ne 0 ]; then say "snapshot failed (exit $code)"; exit "$code"; fi
cleanup_locks

# ---- Phase 3: classify -----------------------------------------------------
say "classify (min-days=$MIN_DAYS, follower-threshold=$FOLLOWER_THRESHOLD)..."
node "$SCRIPTS/classify.cjs" --date="$DATE" --min-days="$MIN_DAYS" --follower-threshold="$FOLLOWER_THRESHOLD"

# ---- Phase 4: refresh follower counts for past-wait accounts, then re-classify
NEED_REFRESH=$(node -e "try{const o=require('$XU_DATA_DIR/reports/non-recip-reasons-$DATE.json');process.stdout.write(String((o.rows||[]).filter(r=>r.needs_profile_refresh).length))}catch(e){process.stdout.write('0')}")
if [ "${NEED_REFRESH:-0}" -gt 0 ]; then
  say "refreshing public follower counts for $NEED_REFRESH past-wait accounts..."
  node "$SCRIPTS/profile-counts.cjs" --from-classify="$DATE" >/dev/null 2>&1
  say "re-classify after refresh..."
  node "$SCRIPTS/classify.cjs" --date="$DATE" --min-days="$MIN_DAYS" --follower-threshold="$FOLLOWER_THRESHOLD"
fi

CAND=$(node -e "try{const o=require('$XU_DATA_DIR/reports/non-recip-reasons-$DATE.json');process.stdout.write(String((o.rows||[]).filter(r=>r.decision==='candidate_unfollow').length))}catch(e){process.stdout.write('0')}")
say "candidates (ELIGIBLE_FOR_UNFOLLOW): ${CAND:-0}"

# ---- Phase 5: report or unfollow ------------------------------------------
if [ "$MODE" = "report" ]; then
  say "MODE=report — candidate list written, NOT unfollowing. Files in $XU_DATA_DIR/reports/"
  node -e "
    const o=require('$XU_DATA_DIR/reports/non-recip-reasons-$DATE.json');
    console.log('  reason breakdown:', JSON.stringify(o.totals.byReason));
    const c=(o.rows||[]).filter(r=>r.decision==='candidate_unfollow');
    console.log('  candidate_unfollow:', c.length);
    c.slice(0,50).forEach(r=>console.log('   - @'+r.handle+'  followers='+r.refreshed_followers_count+'  elapsed='+r.natural_elapsed_days+'d'));
  "
  exit 0
fi

# MODE=unfollow
if [ "${CAND:-0}" -eq 0 ]; then say "no candidates to unfollow — done."; exit 0; fi
cleanup_locks
say "MODE=unfollow — executing unfollows (LIMIT=$LIMIT, DRY_RUN=${DRY_RUN:-0})..."
LIMIT_ARG=""; [ "$LIMIT" -gt 0 ] && LIMIT_ARG="--limit=$LIMIT"
MY_HANDLE="$MY_HANDLE" node "$SCRIPTS/unfollow.cjs" --date="$DATE" $LIMIT_ARG
code=$?; halt_on_anomaly "$code"
if [ "$code" -ne 0 ]; then say "unfollow exited $code"; exit "$code"; fi
cleanup_locks

# verify (and one retry pass for stragglers)
for vpass in 1 2; do
  say "verify-unfollow pass $vpass..."
  node "$SCRIPTS/verify-unfollow.cjs" --date="$DATE" >/dev/null 2>&1
  STILL=$(node -e "try{const o=require('$XU_DATA_DIR/reports/verify-unfollow-$DATE.json');process.stdout.write(String((o.results||[]).filter(r=>!r.not_following).length))}catch(e){process.stdout.write('0')}")
  say "  still following after pass $vpass: ${STILL:-0}"
  [ "${STILL:-0}" -eq 0 ] && break
  cleanup_locks
done

say "=== DONE ==="
node -e "
  const u=require('$XU_DATA_DIR/reports/unfollow-$DATE.json');
  const c={}; (u.results||[]).forEach(r=>c[r.action]=(c[r.action]||0)+1);
  console.log('  unfollow actions:', JSON.stringify(c));
  try{const v=require('$XU_DATA_DIR/reports/verify-unfollow-$DATE.json');
    console.log('  verified not_following:', (v.results||[]).filter(r=>r.not_following).length+'/'+(v.results||[]).length);}catch(e){}
"
[ -f "$ALERT" ] && say "NOTE: ALERT.txt present — review it."
exit 0
