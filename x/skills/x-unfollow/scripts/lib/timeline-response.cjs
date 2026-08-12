'use strict';

const { HANDLE_RE, normalizeHandle, isNavOrMiscrape } = require('./hygiene.cjs');

function operationFromUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (!['x.com', 'www.x.com'].includes(url.hostname.toLowerCase())) return null;
    const operation = url.pathname.split('/').filter(Boolean).at(-1) || '';
    return ['Followers', 'Following'].includes(operation) ? operation : null;
  } catch { return null; }
}

function requestCursorFromUrl(rawUrl) {
  try {
    const variables = JSON.parse(new URL(rawUrl).searchParams.get('variables') || '{}');
    return typeof variables.cursor === 'string' && variables.cursor ? variables.cursor : null;
  } catch { return null; }
}

function timelineEntries(payload) {
  const entries = [];
  let found = false;
  const visited = new Set();
  const visit = (value) => {
    if (!value || typeof value !== 'object' || visited.has(value)) return;
    visited.add(value);
    if (Array.isArray(value)) {
      if (value.some((item) => item?.content?.entryType)) entries.push(...value);
      else for (const item of value) visit(item);
      return;
    }
    for (const [key, child] of Object.entries(value)) {
      if (key === 'entries' && Array.isArray(child)) {
        found = true;
        entries.push(...child);
      } else visit(child);
    }
  };
  visit(payload);
  return { entries, found };
}

function unwrapUserResult(value) {
  let current = value;
  for (let i = 0; i < 3 && current?.result && !current.core && !current.legacy; i++) current = current.result;
  return current;
}

function parseUserEntry(entry, listType) {
  if (entry?.content?.entryType !== 'TimelineTimelineItem') return null;
  const item = entry.content.itemContent || entry.content.item?.itemContent;
  if (item?.itemType !== 'TimelineUser') return null;
  const user = unwrapUserResult(item.user_results || item.userResults);
  const handle = String(user?.core?.screen_name || user?.legacy?.screen_name || '').replace(/^@/, '').trim();
  if (!HANDLE_RE.test(handle) || isNavOrMiscrape(handle)) return null;
  const name = String(user?.core?.name || user?.legacy?.name || handle).trim() || handle;
  const row = { handle, name };
  if (listType === 'following' && typeof user?.relationship_perspectives?.followed_by === 'boolean') {
    row.isFollowingMe = user.relationship_perspectives.followed_by;
  }
  return row;
}

function extractTimelineResponse(payload, { listType = 'followers' } = {}) {
  if (!['followers', 'following'].includes(listType)) throw new Error('invalid list type');
  if (Array.isArray(payload?.errors) && payload.errors.length) throw new Error('GRAPHQL_ERRORS');
  const timeline = timelineEntries(payload);
  if (!timeline.found) throw new Error('TIMELINE_ENTRIES_NOT_FOUND');
  const rows = new Map();
  let bottomCursor = null;
  let topCursor = null;
  for (const entry of timeline.entries) {
    const content = entry?.content;
    if (content?.entryType === 'TimelineTimelineCursor') {
      if (content.cursorType === 'Bottom' && typeof content.value === 'string' && content.value) bottomCursor = content.value;
      if (content.cursorType === 'Top' && typeof content.value === 'string' && content.value) topCursor = content.value;
      continue;
    }
    const row = parseUserEntry(entry, listType);
    if (!row) continue;
    const key = normalizeHandle(row.handle);
    const previous = rows.get(key);
    if (!previous) rows.set(key, row);
    else if (row.isFollowingMe === true && previous.isFollowingMe !== true) previous.isFollowingMe = true;
  }
  return { rows: [...rows.values()], bottomCursor, topCursor, terminal: bottomCursor === null };
}

function initialCursorState() {
  return {
    responsesSeen: 0,
    userEntriesSeen: 0,
    cursorPages: 0,
    duplicateResponses: 0,
    repeatedTerminalAttempts: 0,
    expectedRequestCursor: null,
    cursorChainComplete: false,
    terminalReason: null,
    seenPageKeys: [],
    seenBottomCursors: [],
  };
}

function advanceCursorState(state, page) {
  const requestCursor = typeof page.requestCursor === 'string' && page.requestCursor ? page.requestCursor : null;
  const bottomCursor = typeof page.bottomCursor === 'string' && page.bottomCursor ? page.bottomCursor : null;
  const userCount = Number.isInteger(page.userCount) && page.userCount >= 0 ? page.userCount : 0;
  const newUniqueCount = Number.isInteger(page.newUniqueCount) && page.newUniqueCount >= 0 ? page.newUniqueCount : 0;
  const next = {
    ...state,
    responsesSeen: state.responsesSeen + 1,
    userEntriesSeen: state.userEntriesSeen + userCount,
    seenPageKeys: [...state.seenPageKeys],
    seenBottomCursors: [...state.seenBottomCursors],
  };

  if (bottomCursor !== null && bottomCursor === requestCursor) {
    if (newUniqueCount > 0) throw new Error(`CURSOR_LOOP: ${bottomCursor}`);
    next.repeatedTerminalAttempts = state.repeatedTerminalAttempts + 1;
    next.expectedRequestCursor = requestCursor;
    if (next.repeatedTerminalAttempts >= 2) {
      next.cursorChainComplete = true;
      next.terminalReason = 'repeated_cursor_no_new';
    }
    return next;
  }

  const pageKey = `${requestCursor || '<initial>'}->${bottomCursor || '<terminal>'}`;
  if (state.seenPageKeys.includes(pageKey)) {
    next.duplicateResponses = state.duplicateResponses + 1;
    return next;
  }
  if (state.cursorPages > 0 && requestCursor !== state.expectedRequestCursor) {
    throw new Error(`CURSOR_CHAIN_BROKEN: expected ${state.expectedRequestCursor || '<initial>'}, got ${requestCursor || '<initial>'}`);
  }
  if (bottomCursor !== null && state.seenBottomCursors.includes(bottomCursor)) throw new Error(`CURSOR_LOOP: ${bottomCursor}`);

  next.seenPageKeys.push(pageKey);
  if (bottomCursor !== null) next.seenBottomCursors.push(bottomCursor);
  next.cursorPages = state.cursorPages + 1;
  next.repeatedTerminalAttempts = 0;
  next.expectedRequestCursor = bottomCursor;
  if (bottomCursor === null) {
    next.cursorChainComplete = true;
    next.terminalReason = 'no_bottom_cursor';
  }
  return next;
}

module.exports = {
  operationFromUrl,
  requestCursorFromUrl,
  extractTimelineResponse,
  initialCursorState,
  advanceCursorState,
};
