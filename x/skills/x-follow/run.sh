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
# Query POOL (was 6 near-duplicate terms hammered every round). Wider + more varied so each
# rotating slice reaches a fresher account population — the old set's results overlapped ~61%
# (dup) and re-surfaced the same already-decided handles. QUERIES_PER_ROUND of these run each
# round, rotating by round number, so all terms are covered across a few rounds while each
# round stays small enough to dodge the f=live 429 wall.
QUERIES="${QUERIES:-求互关,互相关注,回关,求关注,蓝V互关,蓝V互粉,互粉,回粉,互关注,求关注回关,涨粉互关,蓝V互粉互关,求互fo,互关必回}"
QUERIES_PER_ROUND="${QUERIES_PER_ROUND:-4}"
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
# FERS_MAX 3000 (was 1100): 1100 over-rejected blue-V accounts (they skew to more followers).
# FOLLOW_RATIO_MIN 0.5: reject only one-way broadcasters (fing < fers*0.5), not every account
# whose followers slightly exceed following. Both feed campaign AND the threshold-aware skip
# release in build-queue (previously over-rejected handles re-surface when the cap rises).
FERS_MAX="${FERS_MAX:-3000}"
FOLLOW_RATIO_MIN="${FOLLOW_RATIO_MIN:-0.5}"
HARVEST_SCROLLS="${HARVEST_SCROLLS:-18}"
MAX_CAMPAIGN_ATTEMPTS="${MAX_CAMPAIGN_ATTEMPTS:-12}"
NEED=$(( TARGET * CAND_MULT ))
SOFT_TTL_DAYS="${SOFT_TTL_DAYS:-30}"
# Verified-only preset (default). When on, drop harvested non-blue candidates at queue-build
# time (DROP_NONBLUE) so they never cost a campaign profile visit just to be rejected.
VERIFIED_REQUIRED="${VERIFIED_REQUIRED:-true}"
if [ "$VERIFIED_REQUIRED" = "true" ]; then DROP_NONBLUE=1; else DROP_NONBLUE=0; fi
# Pool-exhaustion guard: stop after this many consecutive harvest rounds that add fewer
# than POOL_MIN_GAIN new candidates (the search pool has run dry — looping wastes 浏览器
# 开关 + 限流配额, exactly the 1.5h空转 seen before).
POOL_DRY_ROUNDS="${POOL_DRY_ROUNDS:-2}"
POOL_MIN_GAIN="${POOL_MIN_GAIN:-5}"
# Rate-limit recovery: a low-yield round caused by 429 is NOT pool exhaustion. When harvest
# reports rateLimited, cool down ROUND_COOLDOWN_RL_S and retry (up to MAX_RL_RETRIES) WITHOUT
# counting it toward POOL_DRY_ROUNDS — so a throttled run no longer bails early as "exhausted".
ROUND_COOLDOWN_RL_S="${ROUND_COOLDOWN_RL_S:-300}"
MAX_RL_RETRIES="${MAX_RL_RETRIES:-3}"
export SKIP_GLOB SOFT_TTL_DAYS DROP_NONBLUE VERIFIED_REQUIRED FERS_MAX FOLLOW_RATIO_MIN

mkdir -p "$JOB_DIR"
TRACKER="$JOB_DIR/tracker.json"
QUEUE="$JOB_DIR/queue.json"
LOG="$JOB_DIR/campaign.log"
ALERT="$JOB_DIR/ALERT.txt"
PID_FILE="$JOB_DIR/run.pid"
STATUS="$JOB_DIR/status.json"
export PROFILE_DIR TRACKER_PATH="$TRACKER" QUEUE_PATH="$QUEUE" LOG_PATH="$LOG" ALERT_PATH="$ALERT" STATUS_PATH="$STATUS" JOB_DIR
say() { echo "[run $(date +%H:%M:%S)] $*"; }
# Single-line progress the human (and Claude) can read any time without tailing logs.
# campaign.cjs writes the same file per-account; run.sh writes it at phase boundaries.
status() {  # status <phase> <extra-msg>
  node -e "require('fs').writeFileSync('$STATUS', JSON.stringify({phase:process.argv[1], msg:process.argv[2], followed:(()=>{try{return JSON.parse(require('fs').readFileSync('$TRACKER')).followed.length}catch(e){return 0}})(), target:$TARGET, ts:new Date().toISOString()},null,2))" "$1" "${2:-}" 2>/dev/null || true
}

# Write own PID so callers can stop the whole process tree reliably.
echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT
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

# ---- Phase 2: tracker init -------------------------------------------------
# The new tracker holds ONLY this run's decisions. The historical skip-set is NO LONGER
# frozen in here as `pre_existing` (which bloated trackers and erased the reason/timestamp
# tiered-release needs). Instead build-queue derives the live, tiered skip-set from
# SKIP_GLOB on every queue build, automatically reclaiming误杀的瞬时错误 + 过期阈值拒绝.
if [ ! -f "$TRACKER" ]; then
  node -e "require('fs').writeFileSync('$TRACKER',JSON.stringify({followed:[],rejected:[],stats:{profiles_checked:0,follow_success:0}}))"
fi
SKIP_N=$(node -e "
  const {buildSkipSetFromPaths}=require('$SCRIPTS/lib/skipset.cjs');
  const fs=require('fs');
  const paths=Array.from(fs.globSync('$SKIP_GLOB'));
  const stats={};
  const skip=buildSkipSetFromPaths(paths,{softTtlDays:$SOFT_TTL_DAYS,fersMax:$FERS_MAX,followRatioMin:$FOLLOW_RATIO_MIN,stats});
  process.stderr.write('[skipset] trackers='+paths.length+' active-skip='+skip.length+' released='+JSON.stringify(stats)+'\n');
  process.stdout.write(String(skip.length));
" 2>>"$JOB_DIR/run.log")
say "starting followed=$(followed)/$TARGET, active skip-set=$SKIP_N (tiered: transient+expired released)"
status init "skip-set=$SKIP_N"

# ---- harvest helper: ALL queries in ONE browser session, then rebuild queue ----
# PERF/SAFETY: one launchPersistentContext for the whole query set (was: one per query =
# ~6 cold Chrome starts + a 429 burst each round). Sets QSZ to the rebuilt queue size.
queue_size() { node -e "try{process.stdout.write(String(require('$QUEUE').length))}catch(e){process.stdout.write('0')}"; }
# Rotating query slice: QUERIES_PER_ROUND terms from the pool, offset by round, wrapping —
# so consecutive rounds search DIFFERENT terms (fresh accounts) instead of re-running all 6.
select_queries() {
  node -e "
    const all='$QUERIES'.split(',').map(s=>s.trim()).filter(Boolean);
    const per=$QUERIES_PER_ROUND, r=parseInt('$1',10)||1;
    const start=((r-1)*per)%all.length, out=[];
    for(let k=0;k<per&&k<all.length;k++) out.push(all[(start+k)%all.length]);
    process.stdout.write(out.join(','));
  " "$1"
}
QSZ=0
RL=0
harvest_round() {
  local round="$1"
  local out="$JOB_DIR/cand-r${round}.json"
  if [ ! -f "$out" ]; then
    cleanup_locks
    local subset; subset=$(select_queries "$round")
    say "harvest[$round]: rotating slice [$subset] (split into ${QUERIES_PER_ROUND}-query sessions)"
    status harvest "round $round"
    PROFILE_DIR="$PROFILE_DIR" node "$SCRIPTS/harvest.cjs" search-multi "$subset" "$HARVEST_SCROLLS" > "$out" 2>"$JOB_DIR/harvest.err"
    local c; c=$(node -e "try{console.log(require('$out').count||0)}catch(e){console.log(0)}")
    say "  -> $c raw merged (deduped across queries)"
  fi
  # Was this round throttled? harvest emits rateLimited so the loop can cool down instead of
  # mis-reading a 429 round as pool exhaustion.
  RL=$(node -e "try{console.log(require('$out').rateLimited?1:0)}catch(e){console.log(0)}")
  NOCRYPTO="$NOCRYPTO" JOB_DIR="$JOB_DIR" node "$SCRIPTS/build-queue.cjs" >/dev/null 2>"$JOB_DIR/build-queue.err"
  QSZ=$(queue_size)
  say "  queue=$QSZ / need $NEED (rate-limited=$RL)"
}

# ---- Phase 3+4+5: harvest -> campaign -> verify, looping until target -------
attempt=0
dry_rounds=0
rl_retries=0
while [ "$(followed)" -lt "$TARGET" ]; do
  attempt=$((attempt+1))
  if [ "$attempt" -gt "$MAX_CAMPAIGN_ATTEMPTS" ]; then say "max attempts ($MAX_CAMPAIGN_ATTEMPTS) reached, stopping at $(followed)/$TARGET"; break; fi

  # ensure enough candidates
  QSZ=$(queue_size)
  if [ "${QSZ:-0}" -lt "$NEED" ]; then
    harvest_round "$attempt"
    if [ "${QSZ:-0}" -lt "$POOL_MIN_GAIN" ]; then
      # Low yield has TWO distinct causes — don't conflate them:
      #   (1) rate-limited (429): the pool isn't dry, X is throttling. Cool down + retry.
      #   (2) genuinely dry: the search pool has no fresh accounts. Count toward the bail.
      if [ "$RL" = "1" ]; then
        rl_retries=$((rl_retries+1))
        say "  low yield ($QSZ) but harvest was RATE-LIMITED (429) — NOT pool-dry. cooldown ${ROUND_COOLDOWN_RL_S}s (retry $rl_retries/$MAX_RL_RETRIES)"
        status cooldown "rate-limited, cooling ${ROUND_COOLDOWN_RL_S}s ($rl_retries/$MAX_RL_RETRIES)"
        if [ "$rl_retries" -ge "$MAX_RL_RETRIES" ]; then
          say "RATE-LIMIT persists after $MAX_RL_RETRIES cooldowns — stopping at $(followed)/$TARGET (X is throttling; try again later)."
          status halted_rl "rate-limited at $(followed)/$TARGET"
          break
        fi
        sleep "$ROUND_COOLDOWN_RL_S"
        continue
      fi
      # Pool-exhaustion guard: a clean (non-429) harvest that still yields almost nothing means
      # the search pool is dry — count consecutive dry rounds and bail before空转 hours away.
      dry_rounds=$((dry_rounds+1))
      say "  pool low ($QSZ<$POOL_MIN_GAIN) — dry round $dry_rounds/$POOL_DRY_ROUNDS"
      if [ "$dry_rounds" -ge "$POOL_DRY_ROUNDS" ]; then
        say "POOL EXHAUSTED: $POOL_DRY_ROUNDS consecutive dry harvests. Stopping at $(followed)/$TARGET."
        say "  (try again later for fresh posts, or widen QUERIES / lower thresholds)"
        status exhausted "pool dry at $(followed)/$TARGET"
        break
      fi
      # nothing new to follow this round — skip the campaign launch, harvest again next loop
      continue
    else
      dry_rounds=0; rl_retries=0
    fi
  fi

  cleanup_locks
  say "campaign attempt $attempt (followed=$(followed)/$TARGET)..."
  status campaign "attempt $attempt"
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
  status verify "pass $vpass"
  FIX_TRACKER=1 PROFILE_DIR="$PROFILE_DIR" TRACKER_PATH="$TRACKER" \
    node "$SCRIPTS/verify-follows.cjs" --assumed >"$JOB_DIR/verify-$vpass.json" 2>>"$JOB_DIR/verify.err"
  FAILED=$(node -e "try{console.log((require('$JOB_DIR/verify-$vpass.json').failed||[]).length)}catch(e){console.log(0)}")
  say "  unconfirmed=$FAILED, followed now $(followed)/$TARGET"
  if [ "${FAILED:-0}" -eq 0 ] && [ "$(followed)" -ge "$TARGET" ]; then break; fi
  # demoted failures dropped followed below target -> one more campaign top-up,
  # but ONLY if there are still un-processed candidates (else it's a pointless browser open).
  if [ "$(followed)" -lt "$TARGET" ] && [ "$(queue_size)" -gt 0 ]; then
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
status done "followed=$(followed)/$TARGET"
node -e "
  const t=JSON.parse(require('fs').readFileSync('$TRACKER'));
  const a={}; t.followed.forEach(x=>a[x.action]=(a[x.action]||0)+1);
  const nr=(t.rejected||[]);
  const rc={}; nr.forEach(r=>{const k=r.r.split('(')[0];rc[k]=(rc[k]||0)+1});
  console.log('  follows:', t.followed.length, 'actions:', JSON.stringify(a));
  console.log('  new rejects:', nr.length, JSON.stringify(rc));
"
[ -f "$ALERT" ] && { say "NOTE: ALERT.txt present — review it."; }
exit 0
