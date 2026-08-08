#!/bin/bash
# run.sh — x-unfollow end-to-end orchestrator (follow hygiene).
#
# Pipeline:
#   profile check -> exclusive run lock -> snapshot /following -> classify -> refresh follower
#   counts (only past-wait accounts) -> re-classify -> [report | unfollow + verify]
#
# Two modes (MODE env):
#   report  (DEFAULT) — produce snapshot + classification + candidate list, then STOP.
#                       NOTHING is unfollowed. This is "筛选/统计/报告".
#   unfollow          — additionally execute unfollows for ELIGIBLE_FOR_UNFOLLOW, then
#                       verify. Use ONLY when the user explicitly asked to 取关/unfollow.
#
# Safety:
#   - unfollow.cjs clicks ONLY an explicit Unfollow/取消关注 aria-label for the exact
#     target; it rejects misleading Subscribe buttons even when X labels them *-unfollow.
#   - any anomaly (exit 10-14: CAPTCHA/RATE_LIMIT/LOGIN/RESTRICT/WEBDRIVER) -> HALT + ALERT.txt.
#
# Cross-day note: "days not following back" needs multiple daily snapshots to accrue. On a
# fresh XU_DATA_DIR everyone starts as KEEP_WAITING_GT3 until enough days pass.
#
# Key env:
#   MY_HANDLE=you (required)   MODE=report|unfollow      MIN_DAYS=3   FOLLOWER_THRESHOLD=2000
#   REFRESH_TTL_DAYS=30 (reuse a follower count this many days before re-fetching)
#   PROFILE_MAX_PER_RUN=5 (hard policy cap; extra rows remain pending for a later run)
#   XU_DATA_DIR=~/.config/x-unfollow-data   PROFILE_DIR=~/.config/playwright-chrome-profile-campaign
#   LIMIT=5 (hard policy cap)               DRY_RUN=1 (unfollow mode: verify selectors, no click)
#   NODE_PATH must point at a node_modules with playwright (set by caller).
#
# Follower-count reuse: profile-counts.cjs is the slow step (one serial HTTP fetch per
# past-wait account). classify.cjs now reuses any follower count gathered within
# REFRESH_TTL_DAYS, so a re-run only re-fetches accounts that are new or whose count aged
# out. The first run on a fresh data dir is still a full sweep; subsequent runs are cheap.

set -o pipefail
export NO_COLOR=1 NODE_DISABLE_COLORS=1 FORCE_COLOR=0
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"

MY_HANDLE="${MY_HANDLE:-}"
MODE="${MODE:-report}"
MIN_DAYS="${MIN_DAYS:-3}"
FOLLOWER_THRESHOLD="${FOLLOWER_THRESHOLD:-2000}"
REFRESH_TTL_DAYS="${REFRESH_TTL_DAYS:-30}"
PROFILE_MAX_PER_RUN="${PROFILE_MAX_PER_RUN:-5}"
XU_DATA_DIR="${XU_DATA_DIR:-$HOME/.config/x-unfollow-data}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/.config/playwright-chrome-profile-campaign}"
LIMIT="${LIMIT:-5}"
EXPLICIT_HANDLES="${EXPLICIT_HANDLES:-}"
ALLOW_MUTUAL="${ALLOW_MUTUAL:-0}"
DATE="${SNAPSHOT_DATE:-$(TZ=Asia/Shanghai date +%F)}"
ALERT="$XU_DATA_DIR/ALERT.txt"
export XU_DATA_DIR PROFILE_DIR ALERT_PATH="$ALERT" SNAPSHOT_DATE="$DATE"

say() { echo "[run $(date +%H:%M:%S)] $*"; }
cleanup_locks() { pkill -9 -f "user-data-dir=$PROFILE_DIR" 2>/dev/null; rm -f "$PROFILE_DIR"/Singleton* 2>/dev/null; sleep 1; }

if [ -z "$MY_HANDLE" ]; then say "FATAL: MY_HANDLE required (your X handle, no @)"; exit 2; fi
if [ "$MODE" != "report" ] && [ "$MODE" != "unfollow" ]; then say "FATAL: MODE must be 'report' or 'unfollow'"; exit 2; fi
if [ -n "$EXPLICIT_HANDLES" ] && [ "$MODE" != "unfollow" ]; then say "FATAL: MODE=unfollow is required when EXPLICIT_HANDLES is set"; exit 2; fi
if [ "$ALLOW_MUTUAL" = "1" ] && [ -z "$EXPLICIT_HANDLES" ]; then say "FATAL: ALLOW_MUTUAL=1 requires EXPLICIT_HANDLES"; exit 2; fi
if [ -n "$EXPLICIT_HANDLES" ] && ! [[ "$EXPLICIT_HANDLES" =~ ^@?[A-Za-z0-9_]{1,15}(,@?[A-Za-z0-9_]{1,15})*$ ]]; then say "FATAL: EXPLICIT_HANDLES must be a comma-separated handle list"; exit 2; fi
mkdir -p "$XU_DATA_DIR/snapshots" "$XU_DATA_DIR/reports"

# ---- Phase 0: profile ------------------------------------------------------
if [ ! -d "$PROFILE_DIR" ]; then
  say "FATAL: profile copy not found: $PROFILE_DIR"
  say "Create it once (while base profile is NOT in use):"
  say "  cp -R ~/.config/playwright-chrome-profile $PROFILE_DIR && rm -f $PROFILE_DIR/Singleton*"
  exit 3
fi

# ---- Phase 1: local-only preflight + exclusive network-run lock -----------
say "local-only smoke-test (0 X requests)..."
MY_HANDLE="$MY_HANDLE" PROFILE_DIR="$PROFILE_DIR" node "$SCRIPTS/smoke-test.cjs"
SMOKE=$?
if [ "$SMOKE" -ne 0 ]; then say "local preflight RED (exit $SMOKE); no X request was made."; exit "$SMOKE"; fi

# The lock prevents concurrent runs only. It is released on every normal/error exit.
say "claiming exclusive X network-run lock..."
XU_RUN_TOKEN=$(XU_RUN_OWNER_PID=$$ node "$SCRIPTS/run-lock.cjs" claim)
GUARD=$?
if [ "$GUARD" -ne 0 ]; then say "another x-unfollow run is active (exit $GUARD); no X request was made."; exit "$GUARD"; fi
export XU_RUN_TOKEN
release_run_lock() {
  if [ -n "${XU_RUN_TOKEN:-}" ]; then
    node "$SCRIPTS/run-lock.cjs" release "$XU_RUN_TOKEN" >/dev/null 2>&1 || true
    XU_RUN_TOKEN=""
  fi
}
# Keep INT/TERM default termination semantics. EXIT still runs on signal-driven
# shell termination, so the network-run lock is released without swallowing stop.
trap release_run_lock EXIT
cleanup_locks

halt_on_anomaly() { # $1 = exit code from a node browser step
  case "$1" in
    10|11|12|13|14) say "!!! ANOMALY (exit $1) — HALT. See $ALERT. Not operating the account further."; exit "$1" ;;
  esac
}

if [ -n "$EXPLICIT_HANDLES" ]; then
  say "explicit authorized recovery for $EXPLICIT_HANDLES; skipping pre-action snapshot/classification."
  CAND=$(node -e "process.stdout.write(String(process.argv[1].split(',').filter(Boolean).length))" "$EXPLICIT_HANDLES")
else
  # ---- Phase 2: snapshot /following ---------------------------------------
  say "snapshot @$MY_HANDLE /following (date=$DATE)..."
  MY_HANDLE="$MY_HANDLE" node "$SCRIPTS/snapshot.cjs"
  code=$?; halt_on_anomaly "$code"
  if [ "$code" -ne 0 ]; then say "snapshot failed (exit $code)"; exit "$code"; fi
  cleanup_locks

  # ---- Phase 3: classify ---------------------------------------------------
  say "classify (min-days=$MIN_DAYS, follower-threshold=$FOLLOWER_THRESHOLD, refresh-ttl=${REFRESH_TTL_DAYS}d)..."
  node "$SCRIPTS/classify.cjs" --date="$DATE" --min-days="$MIN_DAYS" --follower-threshold="$FOLLOWER_THRESHOLD" --refresh-ttl-days="$REFRESH_TTL_DAYS"

  # ---- Phase 4: refresh missing/stale follower counts, then re-classify ---
  NEED_REFRESH=$(node -e "try{const o=require('$XU_DATA_DIR/reports/non-recip-reasons-$DATE.json');process.stdout.write(String((o.rows||[]).filter(r=>r.needs_profile_refresh).length))}catch(e){process.stdout.write('0')}")
  if [ "${NEED_REFRESH:-0}" -gt 0 ]; then
    say "refreshing at most $PROFILE_MAX_PER_RUN of $NEED_REFRESH pending follower counts at a 30-60s cadence..."
    PROFILE_MAX_PER_RUN="$PROFILE_MAX_PER_RUN" node "$SCRIPTS/profile-counts.cjs" --from-classify="$DATE" >/dev/null
    say "re-classify after refresh..."
    node "$SCRIPTS/classify.cjs" --date="$DATE" --min-days="$MIN_DAYS" --follower-threshold="$FOLLOWER_THRESHOLD" --refresh-ttl-days="$REFRESH_TTL_DAYS"
  else
    say "no accounts need a fresh follower count (all reused within ${REFRESH_TTL_DAYS}d TTL)."
  fi

  CAND=$(node -e "try{const o=require('$XU_DATA_DIR/reports/non-recip-reasons-$DATE.json');process.stdout.write(String((o.rows||[]).filter(r=>r.decision==='candidate_unfollow').length))}catch(e){process.stdout.write('0')}")
fi
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
if [ -n "$EXPLICIT_HANDLES" ]; then
  MY_HANDLE="$MY_HANDLE" ALLOW_MUTUAL="$ALLOW_MUTUAL" node "$SCRIPTS/unfollow.cjs" --date="$DATE" --handles="$EXPLICIT_HANDLES" $LIMIT_ARG
else
  MY_HANDLE="$MY_HANDLE" node "$SCRIPTS/unfollow.cjs" --date="$DATE" $LIMIT_ARG
fi
code=$?; halt_on_anomaly "$code"
if [ "$code" -ne 0 ]; then say "unfollow exited $code"; exit "$code"; fi
cleanup_locks

# One post-action /following scan, then verify every target via a local set difference.
POST_SNAPSHOT_DATE="${DATE}-post-unfollow"
say "post-action snapshot @$MY_HANDLE /following (one list scan for all verification)..."
MY_HANDLE="$MY_HANDLE" SNAPSHOT_DATE="$POST_SNAPSHOT_DATE" node "$SCRIPTS/snapshot.cjs"
code=$?; halt_on_anomaly "$code"
if [ "$code" -ne 0 ]; then say "post-action snapshot failed (exit $code)"; exit "$code"; fi
cleanup_locks
say "verify-unfollow (local set diff; zero additional X requests)..."
if [ -n "$EXPLICIT_HANDLES" ]; then
  node "$SCRIPTS/verify-unfollow.cjs" --date="$DATE" --snapshot-date="$POST_SNAPSHOT_DATE" --handles="$EXPLICIT_HANDLES" >/dev/null
else
  node "$SCRIPTS/verify-unfollow.cjs" --date="$DATE" --snapshot-date="$POST_SNAPSHOT_DATE" >/dev/null
fi
STILL=$(node -e "try{const o=require('$XU_DATA_DIR/reports/verify-unfollow-$DATE.json');process.stdout.write(String((o.results||[]).filter(r=>!r.not_following).length))}catch(e){process.stdout.write('0')}")
say "  still following after verification: ${STILL:-0}"

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
