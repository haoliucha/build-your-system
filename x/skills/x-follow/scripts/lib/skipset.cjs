// lib/skipset.cjs — build the "already decided" skip-set from prior campaign trackers.
//
// WHY a tracker union (not a live /following snapshot): re-attempting an account we
// already follow is a SAFE no-op (campaign reads the profile, sees "正在关注", records
// reject:already_following, never clicks). So the union of followed∪rejected across all
// prior trackers is sufficient AND deterministic (no browser, can't hit the lock
// conflict that a live snapshot can). Followed handles live in `followed[].handle`,
// rejected in `rejected[].h`.

const fs = require('fs');

// PURE: given an array of parsed tracker objects, return the unique skip handle list.
function buildSkipSet(trackers) {
  const skip = new Set();
  for (const t of trackers || []) {
    if (!t) continue;
    for (const f of t.followed || []) {
      const h = f && (f.handle || f.h);
      if (h) skip.add(h);
    }
    for (const r of t.rejected || []) {
      const h = r && (r.h || r.handle);
      if (h) skip.add(h);
    }
  }
  return Array.from(skip);
}

// Impure wrapper: load tracker JSON files by path (missing/corrupt files skipped).
function buildSkipSetFromPaths(paths) {
  const trackers = [];
  for (const p of paths || []) {
    try { trackers.push(JSON.parse(fs.readFileSync(p, 'utf-8'))); }
    catch { /* missing or unreadable — skip */ }
  }
  return buildSkipSet(trackers);
}

module.exports = { buildSkipSet, buildSkipSetFromPaths };
