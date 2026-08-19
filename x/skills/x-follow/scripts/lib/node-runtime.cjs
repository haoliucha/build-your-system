#!/usr/bin/env node
// node-runtime.cjs — fail-closed capability gate for Node APIs used by x-follow.

const fs = require('fs');

function assertNodeRuntime(version = process.versions.node, fsModule = fs) {
  const major = Number.parseInt(String(version).split('.', 1)[0], 10);
  if (!Number.isInteger(major) || major < 22) {
    throw new Error(`x-follow requires Node.js >= 22 (found ${version || 'unknown'})`);
  }
  if (typeof fsModule.globSync !== 'function') {
    throw new Error('x-follow requires Node.js fs.globSync; install Node.js >= 22');
  }
}

if (require.main === module) {
  try { assertNodeRuntime(); }
  catch (error) {
    process.stderr.write(`FATAL: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { assertNodeRuntime };
