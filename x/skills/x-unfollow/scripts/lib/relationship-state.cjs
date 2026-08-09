'use strict';

const { normalizeHandle, addDays, naturalDaysBetween } = require('./hygiene.cjs');

function mapRows(rows) {
  if (!Array.isArray(rows)) return null;
  const map = new Map();
  for (const row of rows) {
    const key = normalizeHandle(row && row.handle);
    if (!key) continue;
    const previous = map.get(key);
    if (!previous) map.set(key, { ...row });
    else if (row.isFollowingMe === true && previous.isFollowingMe !== true) map.set(key, { ...previous, ...row });
  }
  return map;
}

function relationshipFor(inFollowing, inFollowers) {
  if (inFollowing && inFollowers) return 'mutual';
  if (inFollowing) return 'following_only';
  return 'follower_only';
}

function buildRelationships({ previous = [], followingRows, followersRows, followingMeta, followersMeta, observedDate, followingRefreshed = true }) {
  const prior = mapRows(previous) || new Map();
  const following = mapRows(followingRows);
  const followers = mapRows(followersRows);
  const keys = new Set(prior.keys());
  if (following) for (const key of following.keys()) keys.add(key);
  if (followers) for (const key of followers.keys()) keys.add(key);
  const followingDate = (followingMeta && followingMeta.observedDate) || observedDate;
  const rows = [];

  for (const key of [...keys].sort()) {
    const old = prior.get(key) || {};
    const fr = following && following.get(key);
    const fer = followers && followers.get(key);
    const inFollowing = following ? !!fr : !!old.inFollowing;
    const inFollowers = followers ? !!fer : !!old.inFollowers;
    if (!inFollowing && !inFollowers) continue;
    const badge = fr ? (typeof fr.isFollowingMe === 'boolean' ? fr.isFollowingMe : null)
      : (typeof old.followsMeBadge === 'boolean' ? old.followsMeBadge : null);
    const evidenceConflict = inFollowing && typeof badge === 'boolean' && badge !== inFollowers;
    const row = {
      handle: (fr && fr.handle) || (fer && fer.handle) || old.handle || key,
      name: (fr && fr.name) || (fer && fer.name) || old.name || key,
      inFollowing, inFollowers,
      relationship: relationshipFor(inFollowing, inFollowers),
      followingObservedAt: followingMeta ? followingMeta.generatedAt || null : old.followingObservedAt || null,
      followersObservedAt: followersMeta ? followersMeta.generatedAt || null : old.followersObservedAt || null,
      followsMeBadge: badge,
      evidenceConflict,
      refreshedFollowersCount: Number.isFinite(old.refreshedFollowersCount) ? old.refreshedFollowersCount : null,
      refreshedAt: old.refreshedAt || null,
      nonRecipSince: null,
      nonRecipObservedDate: null,
      consecutiveDays: 0,
    };
    if (followingRefreshed && inFollowing && badge === false && !evidenceConflict && followingDate) {
      const adjacent = old.followsMeBadge === false
        && old.nonRecipObservedDate === addDays(followingDate, -1)
        && old.nonRecipSince;
      row.nonRecipSince = adjacent ? old.nonRecipSince : followingDate;
      row.nonRecipObservedDate = followingDate;
      row.consecutiveDays = naturalDaysBetween(row.nonRecipSince, followingDate) + 1;
    } else if (inFollowing && old.nonRecipSince) {
      row.nonRecipSince = old.nonRecipSince;
      row.nonRecipObservedDate = old.nonRecipObservedDate;
      row.consecutiveDays = old.consecutiveDays || 0;
    }
    rows.push(row);
  }
  return {
    rows,
    meta: {
      generatedAt: new Date().toISOString(),
      complete: !!following && !!followers,
      coherent: !!followingMeta && !!followersMeta && followingMeta.runId === followersMeta.runId,
      followingRunId: followingMeta ? followingMeta.runId || null : null,
      followersRunId: followersMeta ? followersMeta.runId || null : null,
      count: rows.length,
    },
  };
}

function diffFollowers({ previousRows, currentRows = [], followingRows = [], scanMeta = {} }) {
  if (!Array.isArray(previousRows)) return { status: 'baseline_created', comparable: false, rows: [] };
  const before = mapRows(previousRows); const now = mapRows(currentRows); const following = mapRows(followingRows) || new Map();
  const changes = [];
  for (const [key, row] of now) if (!before.has(key)) changes.push({ handle: row.handle, name: row.name || row.handle, change: 'new_follower' });
  if (!scanMeta.usableForNegativeDiff) return { status: 'negative_diff_withheld', comparable: false, rows: changes };
  for (const [key, row] of before) {
    if (now.has(key)) continue;
    const evidence = following.get(key);
    let change = 'unresolved_removed';
    if (evidence && evidence.isFollowingMe === false) change = 'confirmed_unfollowed';
    else if (evidence && evidence.isFollowingMe === true) change = 'evidence_conflict';
    changes.push({ handle: row.handle, name: row.name || row.handle, change });
  }
  changes.sort((a, b) => normalizeHandle(a.handle).localeCompare(normalizeHandle(b.handle)));
  return { status: 'compared', comparable: true, rows: changes };
}

function diffFollowing({ previousRows, currentRows = [], scanMeta = {} }) {
  if (!Array.isArray(previousRows)) return { status: 'baseline_created', comparable: false, rows: [] };
  const before = mapRows(previousRows); const now = mapRows(currentRows); const changes = [];
  for (const [key, row] of now) if (!before.has(key)) changes.push({ handle: row.handle, name: row.name || row.handle, change: 'you_followed' });
  if (!scanMeta.usableForNegativeDiff) return { status: 'negative_diff_withheld', comparable: false, rows: changes };
  for (const [key, row] of before) if (!now.has(key)) changes.push({ handle: row.handle, name: row.name || row.handle, change: 'you_unfollowed' });
  changes.sort((a, b) => normalizeHandle(a.handle).localeCompare(normalizeHandle(b.handle)));
  return { status: 'compared', comparable: true, rows: changes };
}

module.exports = { mapRows, buildRelationships, diffFollowers, diffFollowing };
