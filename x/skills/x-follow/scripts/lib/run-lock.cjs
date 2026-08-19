#!/usr/bin/env node
// run-lock.cjs — atomic directory leases for every X-facing x-follow entry point.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const OWNER_FILE = 'owner.json';

function isPidActive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; }
  catch (error) { return error.code === 'EPERM'; }
}

function inspectLock(lockPath) {
  try {
    const stat = fs.lstatSync(lockPath);
    const ownerPath = stat.isDirectory() ? path.join(lockPath, OWNER_FILE) : lockPath;
    try {
      return { state: 'ready', record: JSON.parse(fs.readFileSync(ownerPath, 'utf8')), legacyFile: !stat.isDirectory() };
    } catch {
      // Never delete a directory with a missing/partial owner record: it can be a creator
      // still publishing its atomically-written metadata, or a corrupted lock needing review.
      return { state: 'pending' };
    }
  } catch (error) {
    if (error.code === 'ENOENT') return { state: 'missing' };
    throw error;
  }
}

function readLock(lockPath) {
  const inspected = inspectLock(lockPath);
  return inspected.state === 'ready' ? inspected.record : null;
}

function writeOwner(lockPath, lock) {
  const temp = path.join(lockPath, `${OWNER_FILE}.${lock.token}.tmp`);
  fs.writeFileSync(temp, JSON.stringify(lock) + '\n', { mode: 0o600 });
  fs.renameSync(temp, path.join(lockPath, OWNER_FILE));
}

function createLockDirectory(lockPath, lock) {
  fs.mkdirSync(lockPath, { mode: 0o700 });
  try { writeOwner(lockPath, lock); }
  catch (error) {
    // Retain publication failures so competitors fail closed rather than deleting a creator.
    throw error;
  }
}

function recoveryPathFor(lockPath) { return `${lockPath}.recovery`; }

function recoverStale(lockPath, observed) {
  const recoveryPath = recoveryPathFor(lockPath);
  try { fs.mkdirSync(recoveryPath, { mode: 0o700 }); }
  catch (error) {
    if (error.code === 'EEXIST') throw new Error('network run lock recovery in progress');
    throw error;
  }
  try {
    const current = inspectLock(lockPath);
    if (current.state !== 'ready' || current.record.token !== observed.token || current.record.pid !== observed.pid) {
      throw new Error('network run lock changed during stale recovery');
    }
    if (isPidActive(current.record.pid)) {
      throw new Error(`network run lock already active (pid=${current.record.pid}, jobDir=${current.record.jobDir || 'unknown'})`);
    }
    const quarantine = `${lockPath}.stale-${current.record.token}-${crypto.randomUUID()}`;
    fs.renameSync(lockPath, quarantine);
    return current.record;
  } finally {
    try { fs.rmdirSync(recoveryPath); } catch {}
  }
}

function acquireLock(lockPath, details = {}) {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const lock = {
    pid: Number.isInteger(details.pid) ? details.pid : process.pid,
    token: details.token || crypto.randomUUID(),
    jobDir: details.jobDir || '',
    startedAt: details.startedAt || new Date().toISOString(),
  };
  if (fs.existsSync(recoveryPathFor(lockPath))) throw new Error('network run lock recovery in progress');
  try {
    createLockDirectory(lockPath, lock);
    return { ...lock, recovered: null };
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
  }
  const existing = inspectLock(lockPath);
  if (existing.state !== 'ready') {
    throw new Error('network run lock is initializing or malformed; refusing unsafe recovery');
  }
  if (isPidActive(existing.record.pid)) {
    throw new Error(`network run lock already active (pid=${existing.record.pid}, jobDir=${existing.record.jobDir || 'unknown'})`);
  }
  const recovered = recoverStale(lockPath, existing.record);
  if (fs.existsSync(recoveryPathFor(lockPath))) throw new Error('network run lock recovery in progress');
  try { createLockDirectory(lockPath, lock); }
  catch (error) {
    if (error.code === 'EEXIST') throw new Error('network run lock changed during stale recovery');
    throw error;
  }
  return { ...lock, recovered };
}

function releaseLock(lockPath, token) {
  const existing = readLock(lockPath);
  if (!existing || existing.token !== token) return false;
  fs.rmSync(lockPath, { recursive: true, force: true });
  return true;
}

function acquireOrInheritLock({ lockPath, jobDir, env = process.env }) {
  const inheritedPath = env.X_FOLLOW_NETWORK_LOCK;
  const inheritedToken = env.X_FOLLOW_NETWORK_LOCK_TOKEN;
  if (inheritedPath === lockPath && inheritedToken) {
    const inherited = readLock(lockPath);
    if (inherited && inherited.token === inheritedToken && isPidActive(inherited.pid)) {
      return { lockPath, token: inheritedToken, inherited: true };
    }
  }
  const lock = acquireLock(lockPath, { jobDir });
  return { lockPath, token: lock.token, inherited: false };
}

function installLeaseCleanup(lease) {
  if (lease.inherited) return;
  const cleanup = () => releaseLock(lease.lockPath, lease.token);
  process.once('exit', cleanup);
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.once(signal, () => {
      cleanup();
      process.exit(signal === 'SIGINT' ? 130 : 143);
    });
  }
}

if (require.main === module) {
  const [command, lockPath, value, pidArg] = process.argv.slice(2);
  try {
    if (command === 'acquire') {
      const lock = acquireLock(lockPath, { jobDir: value, pid: pidArg === undefined ? undefined : Number(pidArg) });
      process.stdout.write(lock.token + '\n');
    } else if (command === 'release') {
      process.stdout.write(releaseLock(lockPath, value) ? 'released\n' : 'not-owner\n');
    } else {
      throw new Error('usage: run-lock.cjs acquire <lock-path> <job-dir> [pid] | release <lock-path> <token>');
    }
  } catch (error) {
    process.stderr.write(`FATAL: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { acquireLock, releaseLock, readLock, isPidActive, acquireOrInheritLock, installLeaseCleanup };
