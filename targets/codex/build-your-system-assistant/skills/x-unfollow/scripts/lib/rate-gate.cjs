const os = require('os');
const path = require('path');
const { readOwner, isPidAlive } = require('./run-lock.cjs');

function assertRunToken() {
  const dataDir = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
  const state = readOwner(dataDir);
  const supplied = process.env.XU_RUN_TOKEN || '';
  if (!state || !state.token || supplied !== state.token || !isPidAlive(state.ownerPid)) {
    const error = new Error('X-facing scripts may only run through run.sh while its exclusive network-run lock is active.');
    error.code = 'XU_RATE_GUARD_REQUIRED';
    throw error;
  }
  return state;
}

module.exports = { assertRunToken };
