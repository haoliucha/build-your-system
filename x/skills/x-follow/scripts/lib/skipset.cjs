// lib/skipset.cjs — build the reason-aware "already decided" skip-set from prior trackers.
//
// WHY a tracker union (not a live /following snapshot): re-attempting an account we
// already follow is a SAFE no-op (campaign reads the profile, sees "正在关注", records
// reject:already_following, never clicks). So the union of decisions across all prior
// trackers is deterministic (no browser, can't hit the lock conflict a live snapshot can).
//
// REASON-AWARENESS (the depletion fix): a "reject" is not monolithic. It is one of:
//   - permanent   : we already follow them (pre_existing_follow / already_following) -> always skip
//   - transient   : the account was never actually evaluated (eval_error / cant_parse_stats)
//                   -> NEVER permanently skip; always retry on a later run
//   - config-bound: failed OUR rules at the time (blacklist/crypto, fers>MAX, fing<=fers,
//                   not_blue). Only valid while that rule is unchanged. If the current run
//                   loosens the rule (e.g. FILTER_CRYPTO=0, higher followers_max), the handle
//                   must be RE-EVALUATED, not skipped.
// The old code skipped followed ∪ ALL rejected regardless of reason, so config-bound and
// transient rejects were burned forever — which silently depleted the candidate pool across
// repeated runs and made "opening crypto" a no-op for previously-crypto-rejected accounts.

const fs = require('fs');

// TRANSIENT — technical failures where the account was never decided against the rules.
const TRANSIENT_RE = [/^eval_error\b/, /^reject:cant_parse_stats\b/];

// normalize a reason: drop the "(detail)" suffix and lowercase. e.g.
//   'reject:fers>1100(9000)' -> 'reject:fers>1100'
function normReason(r) { return String(r || '').split('(')[0].trim().toLowerCase(); }

function isTransient(reason) { const n = normReason(reason); return TRANSIENT_RE.some((re) => re.test(n)); }

// Should a rejected handle with this reason still be SKIPPED under the given reeval config?
//   reevalReasons: normalized reason-prefixes to RE-EVALUATE (i.e. do NOT skip).
// Returns true => keep skipping; false => let it back into the pool for re-evaluation.
function shouldSkipReason(reason, reevalReasons = []) {
  const n = normReason(reason);
  if (isTransient(n)) return false;                          // never burn a non-decision
  const reeval = (reevalReasons || []).map(normReason).filter(Boolean);
  if (reeval.some((pre) => n.startsWith(pre))) return false; // rule loosened -> re-evaluate
  return true;                                               // stable rejection / unknown -> skip
}

// PURE: collapse trackers into one decision per handle, preserving the ORIGINAL reject reason
// (later runs re-stamp prior skips as bare 'pre_existing', so we let a real reason win over it).
// A handle followed in ANY tracker collapses to 'pre_existing_follow' (permanent skip).
// Returns a Map(handle -> normalized reason).
function collapseDecisions(trackers) {
  const followed = new Set();
  const reason = new Map();
  for (const t of trackers || []) {
    if (!t) continue;
    for (const f of t.followed || []) { const h = f && (f.handle || f.h); if (h) followed.add(h); }
    for (const r of t.rejected || []) {
      const h = r && (r.h || r.handle); if (!h) continue;
      const rs = normReason(r.r || r.reason) || 'pre_existing';
      const prev = reason.get(h);
      // first write wins, but a real reason overrides a bare pre_existing placeholder
      if (prev === undefined || prev.startsWith('pre_existing')) reason.set(h, rs);
    }
  }
  const out = new Map();
  for (const h of followed) out.set(h, 'pre_existing_follow');
  for (const [h, rs] of reason) if (!followed.has(h)) out.set(h, rs);
  return out;
}

// Reason-preserving seed records for a fresh run's tracker.rejected: [{ h, r }].
// Use this instead of stamping everything 'pre_existing' so a later reason-aware skip can
// recover config-bound/transient handles when the rules change.
function resolveRejections(trackers) {
  return Array.from(collapseDecisions(trackers), ([h, r]) => ({ h, r }));
}

// PURE: given parsed tracker objects, return the unique skip handle list.
//   opts.reeval (alias opts.reevalReasons): reason-prefixes to RE-EVALUATE (exclude from skip).
//   Default [] => skip followed ∪ all rejected, EXCEPT transient reasons (always retried).
function buildSkipSet(trackers, opts = {}) {
  const reeval = opts.reeval || opts.reevalReasons || [];
  const skip = [];
  for (const [h, rs] of collapseDecisions(trackers)) {
    if (rs === 'pre_existing_follow') { skip.push(h); continue; }  // followed -> always skip
    if (shouldSkipReason(rs, reeval)) skip.push(h);
  }
  return skip;
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

module.exports = {
  buildSkipSet, buildSkipSetFromPaths, resolveRejections,
  shouldSkipReason, isTransient, normReason, collapseDecisions,
};
