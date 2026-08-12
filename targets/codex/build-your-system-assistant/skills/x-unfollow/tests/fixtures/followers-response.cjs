'use strict';

function userEntry(index, overrides = {}) {
  const handle = overrides.handle || `User${String(index).padStart(2, '0')}`;
  return {
    entryId: `user-${index}`,
    content: {
      entryType: 'TimelineTimelineItem',
      itemContent: {
        itemType: 'TimelineUser',
        user_results: {
          result: {
            __typename: 'User',
            core: { screen_name: handle, name: overrides.name || `Name ${index}` },
            relationship_perspectives: { followed_by: overrides.followedBy ?? (index % 2 === 0) },
            profile_bio: { description: `private fixture field ${index}` },
          },
        },
      },
    },
  };
}

function cursorEntry(type, value) {
  return {
    entryId: `cursor-${type.toLowerCase()}-${value}`,
    content: {
      entryType: 'TimelineTimelineCursor',
      cursorType: type,
      value,
    },
  };
}

function buildFollowersResponse({ count = 50, bottom = 'bottom-1', top = 'top-1', users = null } = {}) {
  const entries = users || Array.from({ length: count }, (_, index) => userEntry(index));
  if (bottom !== null) entries.push(cursorEntry('Bottom', bottom));
  if (top !== null) entries.push(cursorEntry('Top', top));
  return {
    data: {
      user: {
        result: {
          timeline: {
            timeline: {
              instructions: [{ type: 'TimelineAddEntries', entries }],
            },
          },
        },
      },
    },
  };
}

module.exports = { userEntry, cursorEntry, buildFollowersResponse };
