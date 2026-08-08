'use strict';

function normalizeHandle(value) {
  return String(value || '').trim().replace(/^@/, '').toLowerCase();
}

function uniqueTargets(handles) {
  const seen = new Set();
  const out = [];
  for (const raw of handles || []) {
    const display = String(raw || '').trim().replace(/^@/, '');
    const key = normalizeHandle(display);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push({ display, key });
  }
  return out;
}

function diffFollowing(targetHandles, followingRows) {
  const targets = uniqueTargets(targetHandles);
  const following = new Set((followingRows || []).map((row) => normalizeHandle(
    typeof row === 'string' ? row : row && row.handle,
  )).filter(Boolean));
  const results = targets.map(({ display, key }) => ({
    handle: display,
    not_following: !following.has(key),
    present_in_following: following.has(key),
  }));
  return {
    requested: targets.map((target) => target.display),
    removed: results.filter((row) => row.not_following).map((row) => row.handle),
    remaining: results.filter((row) => !row.not_following).map((row) => row.handle),
    results,
  };
}

function roundOne(value) {
  return Math.round(value * 10) / 10;
}

function coverageSummary(scannedTotal, headerFollowingCount, minCoveragePct = 95) {
  const scanned = Number(scannedTotal);
  const expected = Number(headerFollowingCount);
  const rawCoveragePct = Number.isFinite(scanned) && Number.isFinite(expected) && expected > 0
    ? roundOne((scanned / expected) * 100)
    : null;
  return {
    scannedTotal: Number.isFinite(scanned) ? scanned : null,
    headerFollowingCount: Number.isFinite(expected) && expected > 0 ? expected : null,
    rawCoveragePct,
    coveragePct: rawCoveragePct === null ? null : Math.min(100, rawCoveragePct),
    coverageWarning: rawCoveragePct !== null && rawCoveragePct < minCoveragePct,
  };
}

module.exports = { normalizeHandle, uniqueTargets, diffFollowing, coverageSummary };
