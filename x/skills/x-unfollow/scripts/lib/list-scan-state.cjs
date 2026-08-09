'use strict';

function expectedListPath(handle, listType) {
  const clean = String(handle || '').replace(/^@/, '').trim();
  if (!/^[A-Za-z0-9_]{1,15}$/.test(clean)) throw new Error('invalid handle');
  if (!['following', 'followers'].includes(listType)) throw new Error('invalid list type');
  return `/${clean}/${listType}`;
}

function isExpectedListUrl(rawUrl, handle, listType) {
  try {
    const url = new URL(rawUrl);
    if (!['x.com', 'www.x.com'].includes(url.hostname.toLowerCase())) return false;
    const actual = url.pathname.replace(/\/+$/, '').toLowerCase();
    return actual === expectedListPath(handle, listType).toLowerCase();
  } catch { return false; }
}

function allowedCount(expectedCount) {
  if (!Number.isFinite(expectedCount) || expectedCount <= 0) return null;
  return expectedCount + Math.max(10, Math.ceil(expectedCount * 0.02));
}

function coveragePct(count, expectedCount) {
  if (!Number.isFinite(expectedCount) || expectedCount <= 0) return null;
  return Math.min(100, Math.round(count * 10000 / expectedCount) / 100);
}

function initialProgress({ expectedCount = null, stableLimit = 8, minCoveragePct = 95 } = {}) {
  return {
    expectedCount, stableLimit, minCoveragePct,
    uniqueCount: 0, stableRounds: 0, rounds: 0, recoveries: 0,
    coveragePct: coveragePct(0, expectedCount), stopReason: null,
  };
}

function advanceProgress(state, { uniqueCount }) {
  if (!Number.isInteger(uniqueCount) || uniqueCount < 0) throw new Error('INVALID_COUNT');
  if (uniqueCount < state.uniqueCount) throw new Error(`COUNT_DECREASED: ${uniqueCount} < ${state.uniqueCount}`);
  const ceiling = allowedCount(state.expectedCount);
  if (ceiling !== null && uniqueCount > ceiling) throw new Error(`COUNT_OVERFLOW: ${uniqueCount} > ${ceiling}`);
  const next = { ...state, rounds: state.rounds + 1, uniqueCount };
  next.stableRounds = uniqueCount === state.uniqueCount ? state.stableRounds + 1 : 0;
  next.coveragePct = coveragePct(uniqueCount, state.expectedCount);
  const enoughCoverage = next.coveragePct === null || next.coveragePct >= next.minCoveragePct;
  if (next.stableRounds >= next.stableLimit && enoughCoverage) next.stopReason = 'stable';
  return next;
}

function usableForNegativeDiff(state) {
  return state.stopReason === 'stable' && state.coveragePct !== null && state.coveragePct >= 99;
}

function shouldPauseAfterRound({ round, maxRounds, stopped, every = 10 }) {
  return !stopped && round < maxRounds && round % every === 0;
}

function executedRounds(round) { return round; }

module.exports = {
  expectedListPath, isExpectedListUrl, allowedCount, coveragePct,
  initialProgress, advanceProgress, usableForNegativeDiff,
  shouldPauseAfterRound, executedRounds,
};
