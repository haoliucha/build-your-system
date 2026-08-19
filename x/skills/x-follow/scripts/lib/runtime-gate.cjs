// runtime-gate.cjs — resolve state and secure an inherited-or-owned network lease.

const fs = require('fs');
const path = require('path');
const { acquireOrInheritLock, installLeaseCleanup } = require('./run-lock.cjs');
const { resolveRuntimeState, assertIndependentProfile } = require('./runtime-state.cjs');
const { preflightBrowserConfig } = require('./cdp-browser.cjs');

function assertPluginProvenance() {
  const skillDir = path.resolve(__dirname, '..', '..');
  const provenancePath = path.resolve(skillDir, '..', '..', 'scripts', 'plugin-provenance.cjs');
  if (!fs.existsSync(provenancePath)) {
    const error = new Error('LEGACY_STANDALONE_INSTALL: use $x:x-follow in Codex or /x-follow in Claude Code');
    error.code = 'LEGACY_STANDALONE_INSTALL';
    throw error;
  }
  return require(provenancePath).runtimeProvenance({ skillDir, skill: 'x-follow' });
}

function prepareXFacingRuntime(env = process.env) {
  // Every direct X-facing child entry repeats the plugin check. run.sh is the recommended
  // orchestrator, but a copied standalone child must still fail before account state or locks.
  const provenance = assertPluginProvenance();
  // Account/profile selection must fail before acquiring the network lease or loading
  // Playwright. This also proves the email maps to exactly one system Chrome profile.
  const browser = preflightBrowserConfig(env);
  const profile = assertIndependentProfile(env);
  const state = resolveRuntimeState(env);
  const lease = acquireOrInheritLock({ lockPath: state.lockPath, jobDir: state.jobDir, env });
  installLeaseCleanup(lease);
  return { state, lease, profile, browser, provenance };
}

module.exports = { prepareXFacingRuntime, assertIndependentProfile, assertPluginProvenance };
