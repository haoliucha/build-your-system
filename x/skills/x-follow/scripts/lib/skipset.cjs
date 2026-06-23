// lib/skipset.cjs — build the "already decided" skip-set from prior campaign trackers.
//
// WHY a tracker union (not a live /following snapshot): re-attempting an account we
// already follow is a SAFE no-op (campaign reads the profile, sees "正在关注", records
// reject:already_following, never clicks). So the union of followed∪rejected across all
// prior trackers is sufficient AND deterministic (no browser, can't hit the lock
// conflict that a live snapshot can). Followed handles live in `followed[].handle`,
// rejected in `rejected[].h`.
//
// TIERED RELEASE (why not every reject is permanent):
//   - transient  (eval_error:* / no_follow_btn / cant_parse_stats): the rejection was a
//                 423/429/render glitch, NOT a real disqualification. The account is very
//                 likely eligible. -> NEVER skip; let it be re-evaluated.
//   - soft       (fers>MAX / fing<=fers): a threshold that drifts over time. -> skip while
//                 fresh, but RELEASE it when EITHER (a) the reject is older than softTtlDays
//                 (the account's ratio may have flipped), OR (b) the THRESHOLD itself was
//                 relaxed so the account's STORED stats now pass (e.g. an account rejected as
//                 fers>1100(2362) is released the moment FERS_MAX rises to 3000). (b) is the
//                 "threshold-aware" release: raising FERS_MAX / FOLLOW_RATIO_MIN immediately
//                 re-surfaces the previously over-rejected accounts instead of waiting 30d.
//   - permanent  (not_blue / blacklist / gold_org / already_following / pre_existing):
//                 stable disqualifiers. -> skip forever.
// Reject records written before this change have no `at` timestamp; soft ones without a
// timestamp are kept (conservative — we can't prove they're stale), transient ones are
// released regardless (they were never valid rejections to begin with).

const fs = require('fs');

const TRANSIENT = [/^eval_error:/, /^reject:no_follow_btn/, /^reject:cant_parse_stats/, /^reject:no_username/, /^page_error/];
const SOFT = [/^reject:fers/, /^reject:fing/];

// PURE: classify a reject reason string into a release tier.
function classifyReason(reason) {
  const s = String(reason || '');
  if (TRANSIENT.some((re) => re.test(s))) return 'transient';
  if (SOFT.some((re) => re.test(s))) return 'soft';
  return 'permanent';
}

// PURE: would a SOFT reject pass under the CURRENT thresholds? Parses the follower/following
// counts the reject reason carries and re-applies the live gates. Returns true => release.
//   reject:fers>1100(2362)        -> fers=2362; passes if 2362 <= opts.fersMax
//   reject:fing<=fers(165<=323)   -> fing=165, fers=323 (old label)
//   reject:fing<fers*0.5(165<323) -> fing=165, fers=323 (new label)
//     passes if fers <= fersMax AND fing >= fers * followRatioMin (not a one-way broadcaster)
// When the relevant opt is absent, we cannot prove it now passes -> return false (stay skipped).
function softRejectNowPasses(reason, opts = {}) {
  const s = String(reason || '');
  const mFers = s.match(/^reject:fers>\d+\((\d+)\)/);
  if (mFers) {
    if (opts.fersMax == null) return false;
    return parseInt(mFers[1], 10) <= opts.fersMax;
  }
  const mFing = s.match(/^reject:fing[^(]*\((\d+)\D+?(\d+)\)/);
  if (mFing) {
    const fing = parseInt(mFing[1], 10);
    const fers = parseInt(mFing[2], 10);
    if (opts.fersMax != null && fers > opts.fersMax) return false; // still over the cap
    if (opts.followRatioMin == null) return false;
    return fing >= fers * opts.followRatioMin;
  }
  return false;
}

// PURE: given an array of parsed tracker objects, return the unique skip handle list.
// opts: { now (ms, default Date.now()), softTtlDays (default 30), stats (filled in place),
//         fersMax, followRatioMin (current thresholds -> threshold-aware soft release) }
function buildSkipSet(trackers, opts = {}) {
  const now = opts.now != null ? opts.now : Date.now();
  const ttlMs = (opts.softTtlDays != null ? opts.softTtlDays : 30) * 86400000;
  const stats = opts.stats || {};
  const skip = new Set();
  for (const t of trackers || []) {
    if (!t) continue;
    for (const f of t.followed || []) {
      const h = f && (f.handle || f.h);
      if (h) skip.add(h);
    }
    for (const r of t.rejected || []) {
      const h = r && (r.h || r.handle);
      if (!h) continue;
      const reason = r.r || r.reason;
      const cat = classifyReason(reason);
      if (cat === 'transient') { stats.released_transient = (stats.released_transient || 0) + 1; continue; }
      if (cat === 'soft') {
        const at = r.at ? Date.parse(r.at) : NaN;
        if (!isNaN(at) && (now - at) > ttlMs) { stats.released_soft_expired = (stats.released_soft_expired || 0) + 1; continue; }
        // threshold-aware: the account's stored stats now pass the (relaxed) gates -> re-check
        if (softRejectNowPasses(reason, opts)) { stats.released_threshold = (stats.released_threshold || 0) + 1; continue; }
      }
      skip.add(h);
    }
  }
  return Array.from(skip);
}

// Impure wrapper: load tracker JSON files by path (missing/corrupt files skipped).
function buildSkipSetFromPaths(paths, opts = {}) {
  const trackers = [];
  for (const p of paths || []) {
    try { trackers.push(JSON.parse(fs.readFileSync(p, 'utf-8'))); }
    catch { /* missing or unreadable — skip */ }
  }
  return buildSkipSet(trackers, opts);
}

module.exports = { buildSkipSet, buildSkipSetFromPaths, classifyReason, softRejectNowPasses };
