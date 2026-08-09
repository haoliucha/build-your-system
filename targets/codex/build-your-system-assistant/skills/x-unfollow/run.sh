#!/bin/bash
# x-unfollow v3 — current-only state, staged promotion, one exclusive network run.
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
DATE="${SNAPSHOT_DATE:-$(TZ=Asia/Shanghai date +%F)}"
LIMIT="${LIMIT:-5}"
EXPLICIT_HANDLES="${EXPLICIT_HANDLES:-}"
ALLOW_MUTUAL="${ALLOW_MUTUAL:-0}"
ALERT="$XU_DATA_DIR/ALERT.txt"
export XU_DATA_DIR PROFILE_DIR SNAPSHOT_DATE="$DATE" ALERT_PATH="$ALERT"

say() { echo "[run $(date +%H:%M:%S)] $*"; }
cleanup_browser_locks() { pkill -9 -f "user-data-dir=$PROFILE_DIR" 2>/dev/null || true; rm -f "$PROFILE_DIR"/Singleton* 2>/dev/null || true; }

if [ -z "$MY_HANDLE" ]; then say "FATAL: MY_HANDLE required"; exit 2; fi
case "$MODE" in report|unfollow|followers-report|relationships-report) ;; *) say "FATAL: MODE must be report|unfollow|followers-report|relationships-report"; exit 2 ;; esac
if [ -n "$EXPLICIT_HANDLES" ] && [ "$MODE" != "unfollow" ]; then say "FATAL: MODE=unfollow is required when EXPLICIT_HANDLES is set"; exit 2; fi
if [ "$ALLOW_MUTUAL" = "1" ] && [ -z "$EXPLICIT_HANDLES" ]; then say "FATAL: ALLOW_MUTUAL=1 requires EXPLICIT_HANDLES"; exit 2; fi
if [ -n "$EXPLICIT_HANDLES" ] && ! [[ "$EXPLICIT_HANDLES" =~ ^@?[A-Za-z0-9_]{1,15}(,@?[A-Za-z0-9_]{1,15})*$ ]]; then say "FATAL: invalid EXPLICIT_HANDLES"; exit 2; fi
mkdir -p "$XU_DATA_DIR/current" "$XU_DATA_DIR/reports" "$XU_DATA_DIR/.staging"

if [ ! -d "$PROFILE_DIR" ]; then say "FATAL: profile copy not found: $PROFILE_DIR"; exit 3; fi
say "local-only smoke test (0 X requests)..."
MY_HANDLE="$MY_HANDLE" node "$SCRIPTS/smoke-test.cjs" || exit $?

say "claiming exclusive X network-run lock (concurrency only; no 24-hour cooldown)..."
XU_RUN_TOKEN=$(XU_RUN_OWNER_PID=$$ node "$SCRIPTS/run-lock.cjs" claim)
code=$?; if [ "$code" -ne 0 ]; then say "another x-unfollow run is active (exit $code)"; exit "$code"; fi
export XU_RUN_TOKEN
STAGING_DIR="$XU_DATA_DIR/.staging/$XU_RUN_TOKEN"
export XU_ACTION_REPORT="$STAGING_DIR/unfollow.json" LOG_PATH="$STAGING_DIR/unfollow.log"

cleanup_staging() { [ -n "${STAGING_DIR:-}" ] && rm -rf "$STAGING_DIR"; }
release_run_lock() {
  if [ -n "${XU_RUN_TOKEN:-}" ]; then node "$SCRIPTS/run-lock.cjs" release "$XU_RUN_TOKEN" >/dev/null 2>&1 || true; XU_RUN_TOKEN=""; fi
}
cleanup_and_release() { cleanup_browser_locks; cleanup_staging; release_run_lock; }
trap cleanup_and_release EXIT

halt_browser_step() {
  case "$1" in
    15) say "PAGE_DRIFT (exit 15): controlled page left the target list; old current preserved. See $ALERT"; exit 15 ;;
    17) say "scan rejected (exit 17): low coverage/unstable/count anomaly; old current preserved. See $ALERT"; exit 17 ;;
    10|11|12|13|14|16) say "X anomaly (exit $1); old current preserved. See $ALERT"; exit "$1" ;;
    0) ;;
    *) say "browser step failed (exit $1); old current preserved"; exit "$1" ;;
  esac
}

scan_list() {
  local type="$1"
  say "target list=$type; hard cap=160 rounds; worst case per table≈37–48 minutes; cadence remains 8–12s + 60s every 10 rounds"
  MY_HANDLE="$MY_HANDLE" node "$SCRIPTS/list-snapshot.cjs" --list="$type" --run-id="$XU_RUN_TOKEN"
  local result=$?
  halt_browser_step "$result"
  cleanup_browser_locks
}

promote() {
  node "$SCRIPTS/promote-current.cjs" --list="$1" --run-id="$XU_RUN_TOKEN" || exit $?
}

print_report() {
  local file="$1"
  node -e "const o=require(process.argv[1]); console.log(JSON.stringify({status:o.status||null,comparable:o.comparable??null,count:(o.rows||[]).length,rows:(o.rows||[]).slice(0,100)},null,2))" "$file"
}

if [ "$MODE" = "followers-report" ]; then
  scan_list followers
  promote followers
  say "followers baseline/change report complete; no profile visits and no relationship mutation"
  print_report "$XU_DATA_DIR/reports/latest-follower-changes.json"
  exit 0
fi

if [ "$MODE" = "relationships-report" ]; then
  scan_list following
  scan_list followers
  promote both
  node "$SCRIPTS/classify.cjs" --date="$DATE" --min-days="$MIN_DAYS" --follower-threshold="$FOLLOWER_THRESHOLD"
  say "coherent following+followers union complete"
  exit 0
fi

if [ "$MODE" = "report" ] || { [ "$MODE" = "unfollow" ] && [ -z "$EXPLICIT_HANDLES" ]; }; then
  scan_list following
  promote following
  node "$SCRIPTS/classify.cjs" --date="$DATE" --min-days="$MIN_DAYS" --follower-threshold="$FOLLOWER_THRESHOLD"
fi

if [ "$MODE" = "report" ]; then
  say "MODE=report complete — refreshed following only; no follows/unfollows and no profile pages"
  print_report "$XU_DATA_DIR/reports/latest-non-recip.json"
  exit 0
fi

if [ "$MODE" = "unfollow" ] && [ -z "$EXPLICIT_HANDLES" ]; then
  NEED_REFRESH=$(node -e "const o=require(process.argv[1]);process.stdout.write(String((o.rows||[]).filter(r=>r.needs_profile_refresh).length))" "$XU_DATA_DIR/reports/latest-non-recip.json")
  if [ "${NEED_REFRESH:-0}" -gt 0 ]; then
    say "unfollow eligibility needs follower counts; refreshing at most 5 profiles at the existing 30–60s cadence"
    node "$SCRIPTS/profile-counts.cjs" --from-classify
    code=$?; halt_browser_step "$code"
    node "$SCRIPTS/classify.cjs" --date="$DATE" --min-days="$MIN_DAYS" --follower-threshold="$FOLLOWER_THRESHOLD"
  fi
fi

if [ -n "$EXPLICIT_HANDLES" ]; then
  CAND=$(node -e "process.stdout.write(String(process.argv[1].split(',').filter(Boolean).length))" "$EXPLICIT_HANDLES")
else
  CAND=$(node -e "const o=require(process.argv[1]);process.stdout.write(String((o.rows||[]).filter(r=>r.decision==='candidate_unfollow').length))" "$XU_DATA_DIR/reports/latest-non-recip.json")
fi
if [ "${CAND:-0}" -eq 0 ]; then say "no authorized candidates to unfollow"; exit 0; fi

say "MODE=unfollow — explicit mutation phase; LIMIT=$LIMIT DRY_RUN=${DRY_RUN:-0}"
LIMIT_ARG=""; [ "$LIMIT" -gt 0 ] && LIMIT_ARG="--limit=$LIMIT"
if [ -n "$EXPLICIT_HANDLES" ]; then
  MY_HANDLE="$MY_HANDLE" ALLOW_MUTUAL="$ALLOW_MUTUAL" node "$SCRIPTS/unfollow.cjs" --handles="$EXPLICIT_HANDLES" $LIMIT_ARG
else
  MY_HANDLE="$MY_HANDLE" node "$SCRIPTS/unfollow.cjs" $LIMIT_ARG
fi
code=$?; halt_browser_step "$code"; cleanup_browser_locks

say "one post-action following scan for local bulk verification"
scan_list following
promote following
if [ -n "$EXPLICIT_HANDLES" ]; then
  node "$SCRIPTS/verify-unfollow.cjs" --handles="$EXPLICIT_HANDLES"
else
  node "$SCRIPTS/verify-unfollow.cjs"
fi
code=$?; [ "$code" -ne 0 ] && halt_browser_step "$code"
say "DONE"
