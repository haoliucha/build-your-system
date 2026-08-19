// runtime-gate.cjs — resolve state and secure an inherited-or-owned network lease.

const { acquireOrInheritLock, installLeaseCleanup } = require('./run-lock.cjs');
const { resolveRuntimeState } = require('./runtime-state.cjs');

function prepareXFacingRuntime(env = process.env) {
  const state = resolveRuntimeState(env);
  const lease = acquireOrInheritLock({ lockPath: state.lockPath, jobDir: state.jobDir, env });
  installLeaseCleanup(lease);
  return { state, lease };
}

module.exports = { prepareXFacingRuntime };
