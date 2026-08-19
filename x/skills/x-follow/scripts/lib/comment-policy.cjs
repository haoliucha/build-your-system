#!/usr/bin/env node
// comment-policy.cjs — pure, fail-closed authorization policy for post-follow comments.

function parseBoolean(value, name) {
  if (value === undefined || value === '') return false;
  if (value === 'true' || value === '1') return true;
  if (value === 'false' || value === '0') return false;
  throw new Error(`${name} must be true, false, 1, or 0`);
}

function resolveCommentPolicy(env = process.env) {
  const requested = parseBoolean(env.COMMENT_AFTER_FOLLOW, 'COMMENT_AFTER_FOLLOW');
  if (!requested) return { enabled: false };
  if (env.ALLOW_COMMENT_AFTER_FOLLOW !== '1') {
    throw new Error('COMMENT_AFTER_FOLLOW requires ALLOW_COMMENT_AFTER_FOLLOW=1');
  }
  return { enabled: true };
}

if (require.main === module) {
  try {
    process.stdout.write(JSON.stringify(resolveCommentPolicy()) + '\n');
  } catch (error) {
    process.stderr.write(`FATAL: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { resolveCommentPolicy };
