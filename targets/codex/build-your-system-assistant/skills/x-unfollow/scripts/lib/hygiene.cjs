// lib/hygiene.cjs — PURE, side-effect-free follow-hygiene logic shared across scripts &
// unit tests. Nothing here touches the network, filesystem, or a browser, so every
// function is directly testable in tests/run-tests.cjs.
//
// Two notions of "days not following back":
//   - elapsed: natural days since the account was FIRST seen non-reciprocal (binding gate
//     for unfollow eligibility — mirrors the Codex classify-nonrecip semantics).
//   - streak:  CONSECUTIVE days non-reciprocal ending today (reported for context only).
// The unfollow decision uses `elapsed`, NOT `streak`.

const HANDLE_RE = /^[A-Za-z0-9_]{1,15}$/;

// Handles that are actually page nav / mis-scrapes, never real accounts.
const NAV_OR_MISCRAPE = new Set([
  'i', 'home', 'explore', 'notifications', 'messages', 'settings',
  'compose', 'search', 'jobs', 'login', 'signup',
]);

function normalizeHandle(value) {
  return String(value || '').replace(/^@/, '').trim().toLowerCase();
}

function isValidHandle(handle) {
  return HANDLE_RE.test(String(handle || ''));
}

function isNavOrMiscrape(handle) {
  return NAV_OR_MISCRAPE.has(normalizeHandle(handle));
}

// Natural-day difference between two YYYY-MM-DD dates (UTC midnight), floored.
function naturalDaysBetween(firstDate, lastDate) {
  return Math.floor(
    (Date.parse(`${lastDate}T00:00:00Z`) - Date.parse(`${firstDate}T00:00:00Z`)) / 86400000
  );
}

function addDays(date, days) {
  const d = new Date(`${date}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

// Build per-handle history from a flat list of dated snapshot rows.
// rows: [{ handle, name, followers, isFollowingMe, snapshotDate }]
// Only rows with isFollowingMe === false count toward "not following back".
// Returns Map(normalizedHandle -> { handle, name, firstSeen, lastSeen, lastKnownFollowers }).
function buildHistoryFromSnapshots(rows) {
  const history = new Map();
  for (const rec of rows || []) {
    if (!rec || rec.isFollowingMe !== false) continue;
    const date = rec.snapshotDate;
    if (!date) continue;
    const handle = rec.handle;
    if (!isValidHandle(handle)) continue;
    const key = normalizeHandle(handle);
    const prev = history.get(key) || { handle, name: null, firstSeen: null, lastSeen: null, lastKnownFollowers: null };
    if (!prev.firstSeen || date < prev.firstSeen) prev.firstSeen = date;
    if (!prev.lastSeen || date > prev.lastSeen) {
      prev.lastSeen = date;
      if (rec.name) prev.name = rec.name;
      if (Number.isFinite(rec.followers)) prev.lastKnownFollowers = rec.followers;
    }
    prev.handle = handle;
    if (!prev.name && rec.name) prev.name = rec.name;
    history.set(key, prev);
  }
  return history;
}

// CONSECUTIVE-day streak ending at `today` (or the latest run day) per handle.
// Mirrors the original follow-cleanup report. Used for the human-facing report.
function computeStreaks(rows, today, minStreak = 1) {
  const byHandle = new Map();
  for (const rec of rows || []) {
    if (!rec || !rec.handle || !rec.snapshotDate) continue;
    const key = normalizeHandle(rec.handle);
    if (!byHandle.has(key)) byHandle.set(key, []);
    byHandle.get(key).push(rec);
  }

  const result = [];
  for (const recs of byHandle.values()) {
    recs.sort((a, b) => b.snapshotDate.localeCompare(a.snapshotDate)); // newest first
    const nonRecipDates = new Set(recs.filter((r) => r.isFollowingMe === false).map((r) => r.snapshotDate));
    if (nonRecipDates.size === 0) continue;

    let streak = 0;
    let cursor = today;
    for (let i = 0; i < 365; i++) { // safety cap
      if (nonRecipDates.has(cursor)) { streak++; cursor = addDays(cursor, -1); }
      else break;
    }
    if (streak < minStreak) continue;

    const latest = recs[0];
    const sortedNonRecip = [...nonRecipDates].sort();
    result.push({
      handle: latest.handle,
      name: latest.name || latest.handle,
      followers: Number.isFinite(latest.followers) ? latest.followers : null,
      currentStreak: streak,
      firstSeenNonRecip: sortedNonRecip[0],
      lastSeenNonRecip: sortedNonRecip[sortedNonRecip.length - 1],
      latestSnapshot: latest.snapshotDate,
    });
  }
  result.sort((a, b) => b.currentStreak - a.currentStreak || (b.followers || 0) - (a.followers || 0));
  return result;
}

// PURE decision order — the binding contract for what may be unfollowed.
// f: { validHandle, navOrMiscrape, excluded, elapsed (number|null),
//      hasRefreshed (bool), refreshedFollowers (number|null) }
// cfg: { minDays, followerThreshold }
// Returns { reason_code, reason_label_zh, decision, needs_profile_refresh }.
// Order MUST stay stable (tests assert it). Only ELIGIBLE_FOR_UNFOLLOW => candidate_unfollow.
function classifyDecision(f, cfg) {
  const r = (reason_code, reason_label_zh, decision, needs_profile_refresh) =>
    ({ reason_code, reason_label_zh, decision, needs_profile_refresh });

  if (!f.validHandle) return r('EXCLUDE_INVALID_HANDLE', 'handle 格式无效，不作为账号处理', 'do_not_unfollow', false);
  if (f.navOrMiscrape) return r('EXCLUDE_NAV_OR_MISCRAPE', '页面导航/误抓，不是可取关账号', 'do_not_unfollow', false);
  if (f.excluded) return r('EXCLUDE_ALREADY_UNFOLLOWED', '之前已经验证取关成功，不重复取关', 'do_not_unfollow', false);
  if (f.elapsed === null || f.elapsed <= cfg.minDays) {
    return r('KEEP_WAITING_GT3', `尚未超过 ${cfg.minDays} 个自然日，等待期内`, 'keep_waiting', false);
  }
  if (!f.hasRefreshed || !Number.isFinite(f.refreshedFollowers)) {
    return r('ELIGIBLE_FOR_FOLLOWER_REFRESH', '已超过等待期，但还没有刷新公开主页粉丝数', 'refresh_profile_count', true);
  }
  if (f.refreshedFollowers >= cfg.followerThreshold) {
    return r('EXCLUDE_FOLLOWERS_GE_THRESHOLD', `粉丝数 ${f.refreshedFollowers} 达到或超过阈值 ${cfg.followerThreshold}，不取关`, 'do_not_unfollow', false);
  }
  return r('ELIGIBLE_FOR_UNFOLLOW', `超过等待期且粉丝数 ${f.refreshedFollowers} 低于 ${cfg.followerThreshold}，可取关`, 'candidate_unfollow', false);
}

// Asia/Shanghai YYYY-MM-DD. The ONE impure helper here (reads the clock); kept out of the
// tested decision path — tests pass dates explicitly.
function todayInShanghai() {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date());
  const by = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${by.year}-${by.month}-${by.day}`;
}

module.exports = {
  HANDLE_RE, NAV_OR_MISCRAPE,
  normalizeHandle, isValidHandle, isNavOrMiscrape,
  naturalDaysBetween, addDays,
  buildHistoryFromSnapshots, computeStreaks, classifyDecision,
  todayInShanghai,
};
