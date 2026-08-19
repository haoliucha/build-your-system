// runtime-gate.cjs — resolve state and secure an inherited-or-owned network lease.

const { acquireOrInheritLock, installLeaseCleanup } = require('./run-lock.cjs');
const { resolveRuntimeState, assertIndependentProfile } = require('./runtime-state.cjs');

function prepareXFacingRuntime(env = process.env) {
  const profile = assertIndependentProfile(env);
  const state = resolveRuntimeState(env);
  const lease = acquireOrInheritLock({ lockPath: state.lockPath, jobDir: state.jobDir, env });
  installLeaseCleanup(lease);
  return { state, lease, profile };
}

module.exports = { prepareXFacingRuntime, assertIndependentProfile };
