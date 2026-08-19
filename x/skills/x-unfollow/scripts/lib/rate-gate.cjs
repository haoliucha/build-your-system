const fs = require('fs');
const os = require('os');
const path = require('path');
const { readOwner, isPidAlive } = require('./run-lock.cjs');

function assertPluginProvenance() {
  const skillDir = path.resolve(__dirname, '..', '..');
  const provenancePath = path.resolve(skillDir, '..', '..', 'scripts', 'plugin-provenance.cjs');
  if (!fs.existsSync(provenancePath)) {
    const error = new Error('LEGACY_STANDALONE_INSTALL: use $x:x-unfollow in Codex or /x-unfollow in Claude Code');
    error.code = 'LEGACY_STANDALONE_INSTALL';
    throw error;
  }
  return require(provenancePath).runtimeProvenance({ skillDir, skill: 'x-unfollow' });
}

function assertRunToken() {
  // A valid standalone lock token is insufficient: prove this worker belongs to the complete
  // dual-host plugin before reading run state or reaching any browser/network operation.
  assertPluginProvenance();
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

module.exports = { assertRunToken, assertPluginProvenance };
