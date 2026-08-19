#!/usr/bin/env node
// run-lock.cjs — schema-validated atomic directory leases for X-facing entry points.

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const OWNER_FILE = 'owner.json';
const TOKEN_RE = /^[A-Za-z0-9._:-]{1,200}$/;

function isPidActive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try { process.kill(pid, 0); return true; }
  catch (error) { return error.code === 'EPERM'; }
}

function isOwnerRecord(record) {
  return !!record
    && Number.isInteger(record.pid) && record.pid > 0
    && typeof record.token === 'string' && TOKEN_RE.test(record.token)
    && typeof record.jobDir === 'string'
    && typeof record.startedAt === 'string' && Number.isFinite(Date.parse(record.startedAt));
}

function inspectLock(lockPath) {
  try {
    const stat = fs.lstatSync(lockPath);
    const ownerPath = stat.isDirectory() ? path.join(lockPath, OWNER_FILE) : lockPath;
    let record;
    try { record = JSON.parse(fs.readFileSync(ownerPath, 'utf8')); }
    catch { return { state: 'pending' }; }
    return isOwnerRecord(record)
      ? { state: 'ready', record, legacyFile: !stat.isDirectory() }
      : { state: 'malformed' };
  } catch (error) {
    if (error.code === 'ENOENT') return { state: 'missing' };
    throw error;
  }
}

function readLock(lockPath) {
  const inspected = inspectLock(lockPath);
  return inspected.state === 'ready' ? inspected.record : null;
}

function ownerRecord(details = {}) {
  return {
    pid: Number.isInteger(details.pid) ? details.pid : process.pid,
    token: details.token || crypto.randomUUID(),
    jobDir: details.jobDir || '',
    startedAt: details.startedAt || new Date().toISOString(),
  };
}

function writeOwner(directory, record) {
  const temp = path.join(directory, `${OWNER_FILE}.${record.token}.tmp`);
  fs.writeFileSync(temp, JSON.stringify(record) + '\n', { mode: 0o600 });
  fs.renameSync(temp, path.join(directory, OWNER_FILE));
}

function createDirectoryLease(directory, record) {
  fs.mkdirSync(directory, { mode: 0o700 });
  writeOwner(directory, record);
}

function recoveryPathFor(lockPath) { return `${lockPath}.recovery`; }

function waitForCoordination() {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 5);
}

function replaceStaleMarker(markerPath, observed, replacement) {
  const takeoverPath = `${markerPath}.takeover`;
  const takeover = ownerRecord({ jobDir: replacement.jobDir });
  try { createDirectoryLease(takeoverPath, takeover); }
  catch (error) {
    if (error.code === 'EEXIST') throw new Error('network run lock coordination takeover in progress');
    throw error;
  }
  try {
    const current = inspectLock(markerPath);
    if (current.state !== 'ready' || current.record.token !== observed.token || current.record.pid !== observed.pid) {
      throw new Error('network run lock coordination changed during recovery');
    }
    if (isPidActive(current.record.pid)) throw new Error(`network run lock coordination already active (pid=${current.record.pid})`);
    fs.renameSync(markerPath, `${markerPath}.stale-${current.record.token}-${crypto.randomUUID()}`);
    createDirectoryLease(markerPath, replacement);
  } finally {
    const held = readLock(takeoverPath);
    if (held && held.token === takeover.token && held.pid === takeover.pid) fs.rmSync(takeoverPath, { recursive: true, force: true });
  }
}

function acquireCoordination(lockPath, details = {}, retry = 0) {
  const markerPath = recoveryPathFor(lockPath);
  fs.mkdirSync(path.dirname(markerPath), { recursive: true });
  const record = ownerRecord(details);
  try {
    createDirectoryLease(markerPath, record);
    return { lockPath, markerPath, ...record };
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
  }
  const existing = inspectLock(markerPath);
  if (existing.state !== 'ready') throw new Error('network run lock coordination is initializing or malformed');
  if (isPidActive(existing.record.pid)) {
    if (details.waitForAvailability && retry < 12) { waitForCoordination(); return acquireCoordination(lockPath, details, retry + 1); }
    throw new Error(`network run lock coordination already active (pid=${existing.record.pid})`);
  }
  replaceStaleMarker(markerPath, existing.record, record);
  return { lockPath, markerPath, ...record };
}

function releaseCoordination(lease) {
  const current = inspectLock(lease.markerPath);
  if (!current.record || current.record.token !== lease.token || current.record.pid !== lease.pid) return false;
  fs.renameSync(lease.markerPath, `${lease.markerPath}.released-${lease.token}-${crypto.randomUUID()}`);
  return true;
}

function releaseCoordinationFinally(lease) {
  try { releaseCoordination(lease); } catch {}
}

function createMainLock(lockPath, record) {
  createDirectoryLease(lockPath, record);
}

function acquireLock(lockPath, details = {}, retry = 0) {
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  const record = ownerRecord(details);
  const marker = inspectLock(recoveryPathFor(lockPath));
  if (marker.state !== 'missing') {
    if (marker.state !== 'ready' || isPidActive(marker.record.pid)) {
      if (retry < 12) { waitForCoordination(); return acquireLock(lockPath, details, retry + 1); }
      throw new Error('network run lock coordination in progress');
    }
    const coordination = acquireCoordination(lockPath, { jobDir: record.jobDir });
    try {
      createMainLock(lockPath, record);
      return { ...record, recovered: null };
    } finally { releaseCoordinationFinally(coordination); }
  }
  try {
    createMainLock(lockPath, record);
    return { ...record, recovered: null };
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
  }
  const observed = inspectLock(lockPath);
  if (observed.state === 'missing' && retry < 12) {
    waitForCoordination();
    return acquireLock(lockPath, details, retry + 1);
  }
  if (observed.state !== 'ready') throw new Error('network run lock is initializing or malformed; refusing unsafe recovery');
  if (isPidActive(observed.record.pid)) throw new Error(`network run lock already active (pid=${observed.record.pid}, jobDir=${observed.record.jobDir || 'unknown'})`);
  const coordination = acquireCoordination(lockPath, { jobDir: record.jobDir, waitForAvailability: true });
  try {
    const current = inspectLock(lockPath);
    if (current.state === 'missing') {
      createMainLock(lockPath, record);
      return { ...record, recovered: null };
    }
    if (current.state !== 'ready' || current.record.token !== observed.record.token || current.record.pid !== observed.record.pid) {
      throw new Error('network run lock changed during stale recovery');
    }
    if (isPidActive(current.record.pid)) throw new Error(`network run lock already active (pid=${current.record.pid}, jobDir=${current.record.jobDir || 'unknown'})`);
    fs.renameSync(lockPath, `${lockPath}.stale-${current.record.token}-${crypto.randomUUID()}`);
    createMainLock(lockPath, record);
    return { ...record, recovered: current.record };
  } finally { releaseCoordinationFinally(coordination); }
}

function releaseLock(lockPath, token, pid = process.pid) {
  const coordination = acquireCoordination(lockPath, { jobDir: '' });
  try {
    const current = inspectLock(lockPath);
    if (current.state !== 'ready' || current.record.token !== token || current.record.pid !== pid) return false;
    fs.renameSync(lockPath, `${lockPath}.released-${token}-${crypto.randomUUID()}`);
    return true;
  } finally { releaseCoordinationFinally(coordination); }
}

function acquireOrInheritLock({ lockPath, jobDir, env = process.env }) {
  const inheritedPath = env.X_FOLLOW_NETWORK_LOCK;
  const inheritedToken = env.X_FOLLOW_NETWORK_LOCK_TOKEN;
  if (inheritedPath === lockPath && inheritedToken) {
    const inherited = readLock(lockPath);
    if (inherited && inherited.token === inheritedToken && isPidActive(inherited.pid)) {
      return { lockPath, token: inheritedToken, pid: inherited.pid, inherited: true };
    }
  }
  const lock = acquireLock(lockPath, { jobDir });
  return { lockPath, token: lock.token, pid: lock.pid, inherited: false };
}

function installLeaseCleanup(lease) {
  if (lease.inherited) return;
  const cleanup = () => releaseLock(lease.lockPath, lease.token, lease.pid);
  process.once('exit', cleanup);
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.once(signal, () => { cleanup(); process.exit(signal === 'SIGINT' ? 130 : 143); });
  }
}

if (require.main === module) {
  const [command, lockPath, value, pidArg] = process.argv.slice(2);
  try {
    if (command === 'acquire') process.stdout.write(acquireLock(lockPath, { jobDir: value, pid: pidArg === undefined ? undefined : Number(pidArg) }).token + '\n');
    else if (command === 'release') process.stdout.write(releaseLock(lockPath, value, pidArg === undefined ? process.pid : Number(pidArg)) ? 'released\n' : 'not-owner\n');
    else throw new Error('usage: run-lock.cjs acquire <lock-path> <job-dir> [pid] | release <lock-path> <token> [pid]');
  } catch (error) {
    process.stderr.write(`FATAL: ${error.message}\n`);
    process.exitCode = 2;
  }
}

module.exports = { acquireLock, releaseLock, readLock, inspectLock, isPidActive, acquireCoordination, releaseCoordination, acquireOrInheritLock, installLeaseCleanup };
