'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const LOCK_DIRNAME = '.network-run.lock';
const OWNER_FILENAME = 'owner.json';
const INCOMPLETE_LOCK_GRACE_MS = 30000;
const STATE_FILENAME = 'network-run-state.json';

function writeRunState(dataDir, state) {
  const file = path.join(dataDir, STATE_FILENAME);
  const temp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(temp, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
  fs.renameSync(temp, file);
}

function pathsFor(dataDir) {
  const lockDir = path.join(dataDir, LOCK_DIRNAME);
  return { lockDir, ownerFile: path.join(lockDir, OWNER_FILENAME) };
}

function readOwner(dataDir) {
  const { ownerFile } = pathsFor(dataDir);
  try { return JSON.parse(fs.readFileSync(ownerFile, 'utf8')); } catch { return null; }
}

function isPidAlive(pid) {
  const numeric = Number(pid);
  if (!Number.isSafeInteger(numeric) || numeric <= 0) return false;
  try { process.kill(numeric, 0); return true; } catch (error) { return error && error.code === 'EPERM'; }
}

function lockAgeMs(lockDir, nowMs = Date.now()) {
  try { return Math.max(0, nowMs - fs.statSync(lockDir).mtimeMs); } catch { return Infinity; }
}

function inspectLock(dataDir, nowMs = Date.now()) {
  const { lockDir } = pathsFor(dataDir);
  if (!fs.existsSync(lockDir)) return { active: false, stale: false, owner: null, lockDir };
  const owner = readOwner(dataDir);
  if (!owner) {
    const stale = lockAgeMs(lockDir, nowMs) >= INCOMPLETE_LOCK_GRACE_MS;
    return { active: !stale, stale, owner: null, lockDir };
  }
  const active = isPidAlive(owner.ownerPid);
  return { active, stale: !active, owner, lockDir };
}

function claimLock(dataDir, ownerPid, now = new Date()) {
  fs.mkdirSync(dataDir, { recursive: true });
  const { lockDir, ownerFile } = pathsFor(dataDir);
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      fs.mkdirSync(lockDir);
      const owner = {
        token: crypto.randomUUID(),
        ownerPid: Number(ownerPid),
        startedAt: now.toISOString(),
        policy: 'single-concurrent-network-run',
      };
      fs.writeFileSync(ownerFile, `${JSON.stringify(owner, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' });
      writeRunState(dataDir, { status: 'active', ...owner });
      return owner;
    } catch (error) {
      if (error.code !== 'EEXIST') {
        try { fs.rmSync(lockDir, { recursive: true, force: true }); } catch {}
        throw error;
      }
      const state = inspectLock(dataDir);
      if (state.active) {
        const busy = new Error('another x-unfollow network run is active');
        busy.code = 'XU_RUN_LOCKED';
        busy.owner = state.owner;
        throw busy;
      }
      if (state.stale) {
        fs.rmSync(lockDir, { recursive: true, force: true });
        continue;
      }
    }
  }
  const error = new Error('could not claim x-unfollow network run lock');
  error.code = 'XU_RUN_LOCKED';
  throw error;
}

function releaseLock(dataDir, token) {
  const { lockDir } = pathsFor(dataDir);
  const owner = readOwner(dataDir);
  if (!owner || !token || owner.token !== token) {
    const error = new Error('run-lock token mismatch');
    error.code = 'XU_RUN_LOCK_TOKEN_MISMATCH';
    throw error;
  }
  fs.rmSync(lockDir, { recursive: true, force: true });
  writeRunState(dataDir, { status: 'idle', lastRunToken: owner.token, ownerPid: owner.ownerPid, startedAt: owner.startedAt, finishedAt: new Date().toISOString(), policy: owner.policy });
  return owner;
}

module.exports = {
  LOCK_DIRNAME,
  STATE_FILENAME,
  pathsFor,
  readOwner,
  isPidAlive,
  inspectLock,
  claimLock,
  releaseLock,
};
