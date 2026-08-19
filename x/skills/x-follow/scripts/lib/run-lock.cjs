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
  const hasWorkerPid = record && Object.prototype.hasOwnProperty.call(record, 'workerPid');
  const hasWorkerStartedAt = record && Object.prototype.hasOwnProperty.call(record, 'workerStartedAt');
  return !!record
    && Number.isInteger(record.pid) && record.pid > 0
    && typeof record.token === 'string' && TOKEN_RE.test(record.token)
    && typeof record.jobDir === 'string'
    && typeof record.startedAt === 'string' && Number.isFinite(Date.parse(record.startedAt))
    && hasWorkerPid === hasWorkerStartedAt
    && (!hasWorkerPid || (Number.isInteger(record.workerPid) && record.workerPid > 0
      && typeof record.workerStartedAt === 'string' && Number.isFinite(Date.parse(record.workerStartedAt))));
}

function activeLeasePid(record) {
  if (isPidActive(record.pid)) return record.pid;
  if (record.workerPid && isPidActive(record.workerPid)) return record.workerPid;
  return 0;
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

function leaseIdentityPath(directory, record) {
  const identity = crypto.createHash('sha256').update(`${record.pid}\0${record.token}`).digest('hex').slice(0, 16);
  return path.join(directory, `.lease-${identity}`);
}

function writeOwner(directory, record) {
  const temp = path.join(directory, `${OWNER_FILE}.${record.token}.tmp`);
  const identity = leaseIdentityPath(directory, record);
  const identityTemp = `${identity}.tmp`;
  try {
    fs.writeFileSync(identityTemp, 'lease identity\n', { mode: 0o600 });
    fs.renameSync(identityTemp, identity);
    fs.writeFileSync(temp, JSON.stringify(record) + '\n', { mode: 0o600 });
    fs.renameSync(temp, path.join(directory, OWNER_FILE));
  } catch (error) {
    for (const ownPath of [temp, identityTemp, identity]) {
      try { fs.unlinkSync(ownPath); } catch {}
    }
    throw error;
  }
}

function updateOwner(directory, record) {
  const temp = path.join(directory, `${OWNER_FILE}.${record.token}.${crypto.randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temp, JSON.stringify(record) + '\n', { mode: 0o600 });
    fs.renameSync(temp, path.join(directory, OWNER_FILE));
  } finally {
    try { fs.unlinkSync(temp); } catch {}
  }
}

function createDirectoryLease(directory, record) {
  fs.mkdirSync(directory, { mode: 0o700 });
  try { writeOwner(directory, record); }
  catch (error) {
    // rmdir only removes an empty directory created above; never recursively remove a path
    // that another process may have populated after a failed publication.
    try { fs.rmdirSync(directory); } catch {}
    throw error;
  }
}

function recoveryPathFor(lockPath) { return `${lockPath}.recovery`; }

function waitForCoordination() {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 5);
}

function isolatedPath(directory, kind) {
  return `${directory}.${kind}-${crypto.randomUUID()}`;
}

function cleanupIsolated(directory) {
  try { fs.rmSync(directory, { recursive: true, force: true }); } catch {}
}

function isolateDirectory(directory, kind) {
  const isolated = isolatedPath(directory, kind);
  fs.renameSync(directory, isolated);
  return isolated;
}

function claimFiles(identityPath) {
  try {
    const prefix = `${path.basename(identityPath)}.claim-`;
    return fs.readdirSync(path.dirname(identityPath))
      .filter(name => name.startsWith(prefix))
      .map(name => path.join(path.dirname(identityPath), name));
  } catch { return []; }
}

function claimPid(claimPath, identityPath) {
  const suffix = path.basename(claimPath).slice(`${path.basename(identityPath)}.claim-`.length);
  const pid = Number(suffix.split('-', 1)[0]);
  return Number.isInteger(pid) && pid > 0 ? pid : 0;
}

function acquireTakeover(markerPath, replacement, retry = 0) {
  const takeoverPath = `${markerPath}.takeover`;
  const record = ownerRecord({ jobDir: replacement.jobDir });
  try {
    createDirectoryLease(takeoverPath, record);
    return { takeoverPath, record };
  } catch (error) {
    if (error.code !== 'EEXIST') throw error;
  }
  const observed = inspectLock(takeoverPath);
  if (observed.state !== 'ready') throw new Error('network run lock coordination takeover is initializing or malformed');
  if (isPidActive(observed.record.pid)) throw new Error(`network run lock coordination takeover already active (pid=${observed.record.pid})`);
  const identity = leaseIdentityPath(takeoverPath, observed.record);
  if (!fs.existsSync(identity)) {
    const priorClaim = claimFiles(identity)[0];
    if (!priorClaim) throw new Error('network run lock coordination takeover is missing its identity; refusing unsafe recovery');
    if (isPidActive(claimPid(priorClaim, identity))) throw new Error(`network run lock coordination takeover already active (pid=${claimPid(priorClaim, identity)})`);
    try { fs.renameSync(priorClaim, identity); }
    catch (error) {
      if (error.code === 'ENOENT' || error.code === 'EEXIST') return acquireTakeover(markerPath, replacement, retry + 1);
      throw error;
    }
    return acquireTakeover(markerPath, replacement, retry + 1);
  }
  const claim = `${identity}.claim-${process.pid}-${crypto.randomUUID()}`;
  try { fs.renameSync(identity, claim); }
  catch (error) {
    if (error.code === 'ENOENT' && retry < 12) return acquireTakeover(markerPath, replacement, retry + 1);
    throw error;
  }
  try {
    const current = inspectLock(takeoverPath);
    if (current.state !== 'ready' || current.record.token !== observed.record.token || current.record.pid !== observed.record.pid) {
      throw new Error('network run lock coordination takeover changed during recovery');
    }
    if (isPidActive(current.record.pid)) throw new Error(`network run lock coordination takeover already active (pid=${current.record.pid})`);
    const isolated = isolateDirectory(takeoverPath, 'stale');
    try {
      createDirectoryLease(takeoverPath, record);
      return { takeoverPath, record };
    } finally { cleanupIsolated(isolated); }
  } finally {
    // The claim moves with a successfully isolated directory. If recovery aborted before
    // isolation, removing only this caller's claim lets a later owner retry safely.
    try { fs.unlinkSync(claim); } catch {}
  }
}

function releaseTakeover(lease) {
  const current = inspectLock(lease.takeoverPath);
  if (current.state !== 'ready' || current.record.token !== lease.record.token || current.record.pid !== lease.record.pid) return false;
  const isolated = isolateDirectory(lease.takeoverPath, 'released');
  cleanupIsolated(isolated);
  return true;
}

function replaceStaleMarker(markerPath, observed, replacement) {
  const takeover = acquireTakeover(markerPath, replacement);
  try {
    const current = inspectLock(markerPath);
    if (current.state !== 'ready' || current.record.token !== observed.token || current.record.pid !== observed.pid) {
      throw new Error('network run lock coordination changed during recovery');
    }
    if (isPidActive(current.record.pid)) throw new Error(`network run lock coordination already active (pid=${current.record.pid})`);
    const isolated = isolateDirectory(markerPath, 'stale');
    try { createDirectoryLease(markerPath, replacement); }
    finally { cleanupIsolated(isolated); }
  } finally {
    releaseTakeover(takeover);
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
  if (existing.state !== 'ready') {
    if (details.waitForAvailability && retry < 12) { waitForCoordination(); return acquireCoordination(lockPath, details, retry + 1); }
    throw new Error('network run lock coordination is initializing or malformed');
  }
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
  const isolated = isolateDirectory(lease.markerPath, 'released');
  cleanupIsolated(isolated);
  return true;
}

function releaseCoordinationFinally(lease) {
  try { releaseCoordination(lease); } catch {}
}

function createMainLock(lockPath, record) {
  createDirectoryLease(lockPath, record);
}

function acquireMainUnderCoordination(lockPath, record, expected = null) {
  const current = inspectLock(lockPath);
  if (current.state === 'missing') {
    createMainLock(lockPath, record);
    return { ...record, recovered: null };
  }
  if (current.state !== 'ready') throw new Error('network run lock is initializing or malformed; refusing unsafe recovery');
  const activePid = activeLeasePid(current.record);
  if (activePid) throw new Error(`network run lock already active (pid=${activePid}, jobDir=${current.record.jobDir || 'unknown'})`);
  if (expected && (current.record.token !== expected.token || current.record.pid !== expected.pid)) {
    throw new Error('network run lock changed during stale recovery');
  }
  const isolated = isolateDirectory(lockPath, 'stale');
  try {
    createMainLock(lockPath, record);
    return { ...record, recovered: current.record };
  } finally { cleanupIsolated(isolated); }
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
      return acquireMainUnderCoordination(lockPath, record);
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
  const activePid = activeLeasePid(observed.record);
  if (activePid) throw new Error(`network run lock already active (pid=${activePid}, jobDir=${observed.record.jobDir || 'unknown'})`);
  const coordination = acquireCoordination(lockPath, { jobDir: record.jobDir, waitForAvailability: true });
  try {
    return acquireMainUnderCoordination(lockPath, record, observed.record);
  } finally { releaseCoordinationFinally(coordination); }
}

function releaseLock(lockPath, token, pid = process.pid) {
  const coordination = acquireCoordination(lockPath, { jobDir: '' });
  try {
    const current = inspectLock(lockPath);
    if (current.state !== 'ready' || current.record.token !== token || current.record.pid !== pid) return false;
    if (current.record.workerPid && isPidActive(current.record.workerPid)) return false;
    const isolated = isolateDirectory(lockPath, 'released');
    cleanupIsolated(isolated);
    return true;
  } finally { releaseCoordinationFinally(coordination); }
}

function registerInheritedWorker(lockPath, token, workerPid = process.pid, workerStartedAt = new Date().toISOString()) {
  const coordination = acquireCoordination(lockPath, { jobDir: '' });
  try {
    const current = inspectLock(lockPath);
    if (current.state !== 'ready' || current.record.token !== token || !isPidActive(current.record.pid)) return false;
    if (current.record.workerPid) {
      if (current.record.workerPid === workerPid && current.record.workerStartedAt === workerStartedAt) return true;
      if (isPidActive(current.record.workerPid)) {
        throw new Error(`network run lock already has an active inherited worker (pid=${current.record.workerPid})`);
      }
    }
    updateOwner(lockPath, { ...current.record, workerPid, workerStartedAt });
    return true;
  } finally { releaseCoordinationFinally(coordination); }
}

function releaseInheritedWorker(lockPath, token, workerPid, workerStartedAt) {
  const coordination = acquireCoordination(lockPath, { jobDir: '' });
  try {
    const current = inspectLock(lockPath);
    if (current.state !== 'ready'
      || current.record.token !== token
      || current.record.workerPid !== workerPid
      || current.record.workerStartedAt !== workerStartedAt) return false;
    const { workerPid: ignoredPid, workerStartedAt: ignoredStartedAt, ...owner } = current.record;
    updateOwner(lockPath, owner);
    return true;
  } finally { releaseCoordinationFinally(coordination); }
}

function acquireOrInheritLock({ lockPath, jobDir, env = process.env }) {
  const inheritedPath = env.X_FOLLOW_NETWORK_LOCK;
  const inheritedToken = env.X_FOLLOW_NETWORK_LOCK_TOKEN;
  if (inheritedPath === lockPath && inheritedToken) {
    const inherited = readLock(lockPath);
    if (inherited && inherited.token === inheritedToken && isPidActive(inherited.pid)) {
      const workerStartedAt = new Date().toISOString();
      if (!registerInheritedWorker(lockPath, inheritedToken, process.pid, workerStartedAt)) {
        throw new Error('network run lock owner exited before inherited worker registration');
      }
      return { lockPath, token: inheritedToken, pid: inherited.pid, inherited: true, workerPid: process.pid, workerStartedAt };
    }
  }
  const lock = acquireLock(lockPath, { jobDir });
  return { lockPath, token: lock.token, pid: lock.pid, inherited: false };
}

function installLeaseCleanup(lease) {
  const cleanup = lease.inherited
    ? () => releaseInheritedWorker(lease.lockPath, lease.token, lease.workerPid, lease.workerStartedAt)
    : () => releaseLock(lease.lockPath, lease.token, lease.pid);
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

module.exports = { acquireLock, releaseLock, readLock, inspectLock, isPidActive, acquireCoordination, releaseCoordination, acquireOrInheritLock, installLeaseCleanup, leaseIdentityPath, registerInheritedWorker, releaseInheritedWorker };
