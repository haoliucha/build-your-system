#!/bin/bash
# run.sh — x-follow end-to-end orchestrator.
#
# Runs the full pipeline for one target and recovers from errors on its own:
#   smoke-test -> skip-set/tracker init -> harvest-until-enough -> build-queue
#   -> campaign (watchdog) -> verify assumed & top-up -> report
#
# Anomaly handling:
#   - campaign exits 10-14 (CAPTCHA/RATE_LIMIT/LOGIN/RESTRICT/WEBDRIVER) -> HALT, write
#     ALERT.txt, STOP for human review (never keep operating the account on a real anomaly).
#   - campaign exits 0 with followed<target (queue exhausted) -> harvest more, resume.
#   - campaign exits transient (non-zero, non-anomaly) -> retry after a pause.
#   - 'followed_assumed' entries are verified; failures are demoted and re-followed.
#
# Idempotent: re-running continues from tracker.json (followed accounts are skipped).
#
# Key env (all optional except where noted):
#   TARGET=10                MY_HANDLE=                PROFILE_DIR=~/.config/playwright-chrome-profile-campaign
#   JOB_DIR=$(pwd)/.run      QUERIES="求互关,互相关注,回关,求关注,蓝V互关,蓝V互粉"
#   NOCRYPTO=1               CAND_MULT=8   (harvest until queue >= TARGET*CAND_MULT)
#   SKIP_GLOB="$HOME/.claude/jobs/x-follow-*/tracker.json"   (prior trackers -> skip-set)
#   FERS_MAX=1100            HARVEST_SCROLLS=18        MAX_CAMPAIGN_ATTEMPTS=12
#   NODE_PATH must point at a node_modules with playwright (set by caller).

set -o pipefail
# Disable node's console coloring — colored numbers ("\e[33m0\e[39m") break shell integer tests.
export NO_COLOR=1 NODE_DISABLE_COLORS=1 FORCE_COLOR=0
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$SKILL_DIR/scripts"

TARGET="${TARGET:-10}"
MY_HANDLE="${MY_HANDLE:-}"
PROFILE_DIR="${PROFILE_DIR:-$HOME/.config/playwright-chrome-profile-campaign}"
JOB_DIR="${JOB_DIR:-$(pwd)/.run}"
QUERIES="${QUERIES:-求互关,互相关注,回关,求关注,蓝V互关,蓝V互粉}"
# Crypto/web3 filter: DEFAULT OFF (allow crypto accounts). The skill still SUPPORTS
# filtering — set FILTER_CRYPTO=1 to re-enable the crypto/web3 bio + handle filter.
# Rationale: deep into repeated runs the non-crypto蓝V小号 pool depletes; allowing crypto
# keeps the eligible pool large and the pass rate healthy.
FILTER_CRYPTO="${FILTER_CRYPTO:-0}"
if [ "$FILTER_CRYPTO" = "1" ]; then
  NOCRYPTO=1                                   # build-queue drops crypto handles; campaign uses default crypto blacklist
else
  NOCRYPTO=0                                   # build-queue keeps crypto handles
  export BIO_BLACKLIST="${BIO_BLACKLIST:-__crypto_filter_disabled__}"  # never-matching token disables campaign bio filter
fi
export NOCRYPTO
CAND_MULT="${CAND_MULT:-8}"
SKIP_GLOB="${SKIP_GLOB:-$HOME/.claude/jobs/x-follow-*/tracker.json}"
FERS_MAX="${FERS_MAX:-1100}"
HARVEST_SCROLLS="${HARVEST_SCROLLS:-18}"
MAX_CAMPAIGN_ATTEMPTS="${MAX_CAMPAIGN_ATTEMPTS:-12}"
NEED=$(( TARGET * CAND_MULT ))

mkdir -p "$JOB_DIR"
TRACKER="$JOB_DIR/tracker.json"
QUEUE="$JOB_DIR/queue.json"
LOG="$JOB_DIR/campaign.log"
ALERT="$JOB_DIR/ALERT.txt"
export PROFILE_DIR TRACKER_PATH="$TRACKER" QUEUE_PATH="$QUEUE" LOG_PATH="$LOG" ALERT_PATH="$ALERT" JOB_DIR
say() { echo "[run $(date +%H:%M:%S)] $*"; }
followed() { node -e "try{process.stdout.write(String(JSON.parse(require('fs').readFileSync('$TRACKER')).followed.length))}catch(e){process.stdout.write('0')}" 2>/dev/null || echo 0; }

cleanup_locks() { pkill -9 -f "user-data-dir=$PROFILE_DIR" 2>/dev/null; rm -f "$PROFILE_DIR"/Singleton* 2>/dev/null; sleep 1; }

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
if [ "$SMOKE" -ne 0 ]; then
  say "smoke-test RED (exit $SMOKE) — refusing to launch. Fix env (login/profile) and retry."
  exit "$SMOKE"
fi
cleanup_locks

# ---- Phase 2: skip-set + tracker init --------------------------------------
if [ ! -f "$TRACKER" ]; then
  say "building skip-set from prior trackers ($SKIP_GLOB)..."
  node -e "
    const {buildSkipSetFromPaths}=require('$SCRIPTS/lib/skipset.cjs');
    const fs=require('fs');
    const glob=require('child_process').execSync('ls $SKIP_GLOB 2>/dev/null || true').toString().trim().split('\n').filter(Boolean);
    const skip=buildSkipSetFromPaths(glob);
    const t={followed:[],rejected:skip.map(h=>({h,r:'pre_existing'})),stats:{profiles_checked:0,follow_success:0}};
    fs.writeFileSync('$TRACKER',JSON.stringify(t));
    process.stderr.write('[skipset] prior trackers='+glob.length+' skip='+skip.length+'\n');
  "
fi
say "starting followed=$(followed)/$TARGET, skip-set=$(node -e "console.log((JSON.parse(require('fs').readFileSync('$TRACKER')).rejected||[]).length)")"

# ---- harvest helper: run queries until queue >= NEED -----------------------
IFS=',' read -ra QARR <<< "$QUERIES"
harvest_round() {
  local round="$1"
  local qi=0
  for q in "${QARR[@]}"; do
    qi=$((qi+1))
    local out="$JOB_DIR/cand-r${round}-${qi}.json"
    [ -f "$out" ] && continue
    cleanup_locks
    say "harvest[$round.$qi]: $q"
    PROFILE_DIR="$PROFILE_DIR" node "$SCRIPTS/harvest.cjs" search "$q" "$HARVEST_SCROLLS" > "$out" 2>"$JOB_DIR/harvest.err"
    local c; c=$(node -e "try{console.log(require('$out').count||0)}catch(e){console.log(0)}")
    say "  -> $c raw"
    sleep 8
    NOCRYPTO="$NOCRYPTO" JOB_DIR="$JOB_DIR" node "$SCRIPTS/build-queue.cjs" >/dev/null 2>&1
    local qsz; qsz=$(node -e "try{process.stdout.write(String(require('$QUEUE').length))}catch(e){process.stdout.write('0')}")
    say "  queue=$qsz / need $NEED"
    [ "$qsz" -ge "$NEED" ] && break
  done
}

# ---- Phase 3+4+5: harvest -> campaign -> verify, looping until target -------
attempt=0
while [ "$(followed)" -lt "$TARGET" ]; do
  attempt=$((attempt+1))
  if [ "$attempt" -gt "$MAX_CAMPAIGN_ATTEMPTS" ]; then say "max attempts ($MAX_CAMPAIGN_ATTEMPTS) reached, stopping at $(followed)/$TARGET"; break; fi

  # ensure enough candidates
  QSZ=$(node -e "try{process.stdout.write(String(require('$QUEUE').length))}catch(e){process.stdout.write('0')}")
  if [ "${QSZ:-0}" -lt "$NEED" ]; then harvest_round "$attempt"; fi

  cleanup_locks
  say "campaign attempt $attempt (followed=$(followed)/$TARGET)..."
  TARGET="$TARGET" MY_HANDLE="$MY_HANDLE" FERS_MAX="$FERS_MAX" \
    node "$SCRIPTS/campaign.cjs" >>"$JOB_DIR/campaign.stdout.log" 2>&1
  code=$?
  say "campaign exited code=$code followed=$(followed)/$TARGET"

  case $code in
    0) : ;;  # clean exit — either target reached or queue exhausted; loop re-checks/harvests
    10|11|12|13|14)
      say "!!! ANOMALY (exit $code) — HALT. See $ALERT. Not operating the account further."
      exit "$code" ;;
    *) say "transient exit=$code — pausing 20s then retrying"; sleep 20 ;;
  esac
done

# ---- verify assumed follows & top-up --------------------------------------
for vpass in 1 2 3; do
  cleanup_locks
  say "verify pass $vpass: checking followed_assumed..."
  FIX_TRACKER=1 PROFILE_DIR="$PROFILE_DIR" TRACKER_PATH="$TRACKER" \
    node "$SCRIPTS/verify-follows.cjs" --assumed >"$JOB_DIR/verify-$vpass.json" 2>>"$JOB_DIR/verify.err"
  FAILED=$(node -e "try{console.log((require('$JOB_DIR/verify-$vpass.json').failed||[]).length)}catch(e){console.log(0)}")
  say "  unconfirmed=$FAILED, followed now $(followed)/$TARGET"
  if [ "${FAILED:-0}" -eq 0 ] && [ "$(followed)" -ge "$TARGET" ]; then break; fi
  # demoted failures dropped followed below target -> one more campaign top-up
  if [ "$(followed)" -lt "$TARGET" ]; then
    cleanup_locks
    say "top-up campaign after verify (followed=$(followed)/$TARGET)..."
    POST_CLICK_SETTLE_MS="${POST_CLICK_SETTLE_MS:-6000}" TARGET="$TARGET" MY_HANDLE="$MY_HANDLE" FERS_MAX="$FERS_MAX" \
      node "$SCRIPTS/campaign.cjs" >>"$JOB_DIR/campaign.stdout.log" 2>&1
    tcode=$?
    # SAFETY: a real anomaly during the verify top-up must HALT too (not just the main loop).
    case $tcode in
      10|11|12|13|14) say "!!! ANOMALY (exit $tcode) during verify top-up — HALT. See $ALERT."; exit "$tcode" ;;
    esac
  fi
done

cleanup_locks
say "=== DONE === followed=$(followed)/$TARGET  (tracker: $TRACKER)"
node -e "
  const t=JSON.parse(require('fs').readFileSync('$TRACKER'));
  const a={}; t.followed.forEach(x=>a[x.action]=(a[x.action]||0)+1);
  const nr=(t.rejected||[]).filter(r=>r.r!=='pre_existing');
  const rc={}; nr.forEach(r=>{const k=r.r.split('(')[0];rc[k]=(rc[k]||0)+1});
  console.log('  follows:', t.followed.length, 'actions:', JSON.stringify(a));
  console.log('  new rejects:', nr.length, JSON.stringify(rc));
"
[ -f "$ALERT" ] && { say "NOTE: ALERT.txt present — review it."; }
exit 0
