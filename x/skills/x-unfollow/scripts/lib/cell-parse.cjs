// lib/cell-parse.cjs — PURE, side-effect-free parsing of /following UserCell
// observations into snapshot rows. Nothing here touches the network, filesystem,
// or a browser, so every function is directly testable in tests/run-tests.cjs.
//
// Evidence model (the 2026-07-02 false-positive postmortem):
//   - badge PRESENT ([data-testid="userFollowIndicator"] or "Follows you" text) is
//     DEFINITIVE: the account follows me. A true observation must never be downgraded.
//   - badge ABSENT is only trustworthy on a HYDRATED cell (one that also renders its
//     follow/unfollow action button). A cell with neither badge nor button is a
//     placeholder/ghost and must produce NO observation at all — recording "false"
//     from it is exactly the bug that flagged 72% of mutuals as non-reciprocal.

const { HANDLE_RE, normalizeHandle, isNavOrMiscrape } = require('./hygiene.cjs');

// zh-Hans + en + zh-Hant. Fallback only — the testid indicator dominates.
const FOLLOWS_YOU_RE = /Follows you|关注了你|关注你|跟隨你/;

const AVATAR_PREFIX = 'UserAvatar-Container-';

// 'UserAvatar-Container-Alice_99' -> 'Alice_99' (validated), else null.
function handleFromAvatarTestId(testid) {
  const s = String(testid || '');
  if (!s.startsWith(AVATAR_PREFIX)) return null;
  const h = s.slice(AVATAR_PREFIX.length);
  return HANDLE_RE.test(h) ? h : null;
}

// First href whose first path segment is a valid, non-nav handle.
// '/alice/status/1' -> 'alice'; '/i/premium' and '/notifications' are rejected.
function handleFromHrefs(hrefs) {
  for (const href of hrefs || []) {
    const seg = String(href || '').replace(/^\//, '').split(/[/?#]/)[0];
    if (HANDLE_RE.test(seg) && !isNavOrMiscrape(seg)) return seg;
  }
  return null;
}

// Best-effort follower count from cell text (kept verbatim-in-spirit from the old
// extractor for schema compat; /following cells usually render no count -> 0, and
// the authoritative number comes from profile-counts.cjs later).
function parseFollowersFromText(text) {
  const m = String(text || '').match(/([\d.,]+\s*[KMB万千]?)\s*(关注者|followers?)/i);
  if (!m) return 0;
  const s = m[1].trim().replace(/[,，]/g, '');
  const mm = s.match(/^([\d.]+)\s*([KMB万千]?)$/i);
  if (!mm) return 0;
  let n = parseFloat(mm[1]);
  if (isNaN(n)) return 0;
  const u = (mm[2] || '').toUpperCase();
  if (u === 'K') n *= 1e3;
  else if (u === 'M') n *= 1e6;
  else if (u === 'B') n *= 1e9;
  else if (u === '万') n *= 1e4;
  else if (u === '千') n *= 1e3;
  return Math.round(n);
}

// raw cell observation (collected in the page, decided here):
//   { avatarTestId, hrefs, hasFollowIndicator, hasActionButton, nameText, innerText }
// -> { handle, name, followers, isFollowingMe } | null (null = no usable observation)
function parseCell(raw) {
  if (!raw) return null;
  const handle = handleFromAvatarTestId(raw.avatarTestId) || handleFromHrefs(raw.hrefs);
  if (!handle || isNavOrMiscrape(handle)) return null;
  const isFollowingMe = !!raw.hasFollowIndicator || FOLLOWS_YOU_RE.test(raw.innerText || '');
  // Unhydrated guard: no badge AND no action button -> placeholder/ghost cell.
  // Never derive a "false" from it. (Badge presence alone is definitive.)
  if (!isFollowingMe && !raw.hasActionButton) return null;
  const name = String(raw.nameText || '').trim() || handle;
  return { handle, name, followers: parseFollowersFromText(raw.innerText), isFollowingMe };
}

// everTrue-wins merge into Map(normalizedHandle -> row): a true observation upgrades
// an earlier false; a false NEVER downgrades a true (badge absence may be a render
// race). Keeps the first-seen original-case handle; backfills name/followers.
function mergeObservation(map, row) {
  if (!row) return map;
  const key = normalizeHandle(row.handle);
  if (!key) return map;
  const prev = map.get(key);
  if (!prev) {
    map.set(key, { ...row });
    return map;
  }
  if (row.isFollowingMe && !prev.isFollowingMe) prev.isFollowingMe = true;
  if ((!prev.name || prev.name === prev.handle) && row.name && row.name !== row.handle) prev.name = row.name;
  if (!prev.followers && row.followers) prev.followers = row.followers;
  return map;
}

module.exports = {
  FOLLOWS_YOU_RE,
  handleFromAvatarTestId,
  handleFromHrefs,
  parseFollowersFromText,
  parseCell,
  mergeObservation,
};
