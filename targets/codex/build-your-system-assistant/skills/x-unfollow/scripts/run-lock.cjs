#!/usr/bin/env node
'use strict';

const os = require('os');
const path = require('path');
const { inspectLock, claimLock, releaseLock } = require('./lib/run-lock.cjs');

const dataDir = process.env.XU_DATA_DIR || path.join(os.homedir(), '.config/x-unfollow-data');
const command = process.argv[2] || 'status';

function main() {
  if (command === 'status') {
    const state = inspectLock(dataDir);
    console.log(JSON.stringify({ allowed: !state.active, ...state }, null, 2));
    return;
  }
  if (command === 'claim') {
    const ownerPid = Number(process.env.XU_RUN_OWNER_PID || process.ppid);
    try {
      const owner = claimLock(dataDir, ownerPid);
      console.error(`[run-lock] claimed by pid ${owner.ownerPid} at ${owner.startedAt}`);
      process.stdout.write(`${owner.token}\n`);
    } catch (error) {
      if (error.code === 'XU_RUN_LOCKED') {
        const current = error.owner || {};
        console.error(`[run-lock] REFUSED: another run is active (pid=${current.ownerPid || 'claiming'}, started=${current.startedAt || 'unknown'}).`);
        process.exit(18);
      }
      throw error;
    }
    return;
  }
  if (command === 'release') {
    try {
      releaseLock(dataDir, process.argv[3] || process.env.XU_RUN_TOKEN || '');
      console.error('[run-lock] released');
    } catch (error) {
      if (error.code === 'XU_RUN_LOCK_TOKEN_MISMATCH') {
        console.error('[run-lock] REFUSED: token mismatch; active lock was not removed.');
        process.exit(19);
      }
      throw error;
    }
    return;
  }
  console.error('Usage: run-lock.cjs [status|claim|release [token]]');
  process.exit(2);
}

main();
