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
//                 fresh, but once the reject is older than softTtlDays, release it for a
//                 re-check (the follower/following ratio may have flipped).
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

// PURE: given an array of parsed tracker objects, return the unique skip handle list.
// opts: { now (ms, default Date.now()), softTtlDays (default 30), stats (filled in place) }
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
      const cat = classifyReason(r.r || r.reason);
      if (cat === 'transient') { stats.released_transient = (stats.released_transient || 0) + 1; continue; }
      if (cat === 'soft') {
        const at = r.at ? Date.parse(r.at) : NaN;
        if (!isNaN(at) && (now - at) > ttlMs) { stats.released_soft_expired = (stats.released_soft_expired || 0) + 1; continue; }
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

module.exports = { buildSkipSet, buildSkipSetFromPaths, classifyReason };
