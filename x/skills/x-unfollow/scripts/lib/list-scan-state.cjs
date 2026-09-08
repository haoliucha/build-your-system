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

function stalledWithPendingCursor({
  networkStarted,
  cursorChainComplete,
  expectedRequestCursor,
  noResponseAttempts,
  domStableRounds,
  stableLimit = 8,
}) {
  return networkStarted === true
    && cursorChainComplete !== true
    && typeof expectedRequestCursor === 'string'
    && expectedRequestCursor.length > 0
    && Number.isInteger(noResponseAttempts)
    && noResponseAttempts >= stableLimit
    && Number.isInteger(domStableRounds)
    && domStableRounds >= stableLimit;
}

function baselineCoverageComplete({ count, expectedCount, minCoveragePct = 95 }) {
  if (!Number.isInteger(count) || count < 0 || !Number.isInteger(expectedCount) || expectedCount <= 0) return false;
  const coverage = coveragePct(count, expectedCount);
  const ceiling = allowedCount(expectedCount);
  return coverage !== null && coverage >= minCoveragePct && ceiling !== null && count <= ceiling;
}

// A current, explicitly supplied reference is independent of the historical baseline.
// Integer arithmetic keeps the inclusive 1% boundary from rounding outwards.
function confirmedCountBounds(expectedCount) {
  if (!Number.isSafeInteger(expectedCount) || expectedCount <= 0
      || expectedCount > Math.floor(Number.MAX_SAFE_INTEGER / 101)) throw new Error('EXPECTED_COUNT must be a positive safe integer');
  return { min: Math.ceil(expectedCount * 99 / 100), max: Math.floor(expectedCount * 101 / 100) };
}

function parseExpectedCount(raw, mode) {
  if (raw === undefined || raw === '') return null;
  if (mode !== 'report') throw new Error('EXPECTED_COUNT is only supported in MODE=report (following)');
  if (!/^[1-9]\d*$/.test(String(raw))) throw new Error('EXPECTED_COUNT must be a positive safe integer');
  const value = Number(raw);
  confirmedCountBounds(value);
  return value;
}

function confirmedCountMatches(count, expectedCount) {
  const { min, max } = confirmedCountBounds(expectedCount);
  return Number.isSafeInteger(count) && count >= min && count <= max;
}

function confirmedCountStableBottom({ count, expectedCount, networkStarted, cursorPages,
  noResponseAttempts, domStableRounds, bottomStableRounds, stableLimit = 8 }) {
  const required = Math.max(8, stableLimit);
  return expectedCount !== null && expectedCount !== undefined
    && networkStarted === true && cursorPages > 0
    && noResponseAttempts >= required && domStableRounds >= required && bottomStableRounds >= required
    && confirmedCountMatches(count, expectedCount);
}

module.exports = {
  expectedListPath, isExpectedListUrl, allowedCount, coveragePct,
  initialProgress, advanceProgress, usableForNegativeDiff,
  shouldPauseAfterRound, executedRounds, stalledWithPendingCursor, baselineCoverageComplete,
  confirmedCountBounds, parseExpectedCount, confirmedCountMatches, confirmedCountStableBottom,
};
